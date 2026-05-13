import os
import sys
import json
import ssl
import logging
import requests
import urllib3
import time
from dotenv import load_dotenv
import zcatalyst_sdk

# Silence SDK logging
logging.getLogger('zcatalyst_sdk').setLevel(logging.CRITICAL)

# --- SSL FIX (applies globally) ---
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
try:
    ssl._create_default_https_context = ssl._create_unverified_context
except AttributeError:
    pass

_original_request = requests.Session.request
def _patched_request(self, *args, **kwargs):
    kwargs['verify'] = False
    kwargs.setdefault('timeout', 60)
    return _original_request(self, *args, **kwargs)
requests.Session.request = _patched_request

load_dotenv()


class CatalystClient:
    def __init__(self, app=None):
        self.bucket_name = (
            os.getenv("STRATUS_BUCKET")
            or os.getenv("STRATUS_MASTER")
            or os.getenv("STRATUS_MASTER")
            or "test-scrapper"
        )
        self.client_id     = os.getenv("ZOHO_CLIENT_ID",     "1000.S4UP3226EYHCGYSNF9J2OHC3ATLXMI")
        self.client_secret = os.getenv("ZOHO_CLIENT_SECRET", "22861b6b17c8a89a9542404bd107f747cf70e69b65")
        self.refresh_token = os.getenv("ZOHO_REFRESH_TOKEN", "1000.5229f79b10124d84eef12a293ace021b.2aa65d89def398a2f50b9b367e87b544")
        self.datastore_refresh_token = os.getenv("ZOHO_DATASTORE_REFRESH_TOKEN") or self.refresh_token
        self.environment   = (os.getenv("PROJECT_STAGE") or "Development").lower()
        self.folder_prefix = os.getenv("STRATUS_FOLDER") or ""
        if self.folder_prefix and not self.folder_prefix.endswith('/'):
            self.folder_prefix += '/'
        
        # New: Catalyst Function URL (The bridge to DataStore)
        self.function_base_url = os.getenv(
            "CATALYST_FUNCTION_URL", 
            "https://scrapper-agent-60070821911.development.catalystserverless.in/server/scrapper_agent_function"
        )
        
        self._access_token = None
        self.app = None
        
        try:
            self.app = zcatalyst_sdk.initialize()
        except:
            pass

    def is_local_mode(self):
        """
        Returns True if running in local development mode.
        If running on Catalyst AppSail, it returns False.
        """
        is_local = True
        
        # 1. Check if running on Catalyst AppSail (Cloud)
        if os.getenv("X_CATALYST_APP_NAME") or os.getenv("X_CATALYST_PROJECT_ID"):
            is_local = False

        # 2. Explicit disable flag
        elif os.getenv("DISABLE_CATALYST", "").lower() in ["true", "1", "yes"]:
            is_local = True
        
        # 3. Development stage check
        elif self.environment == "production":
            is_local = False
            
        print(f"[*] Catalyst Environment Detection: {'LOCAL' if is_local else 'CLOUD'}")
        return is_local

    # ── Auth ──────────────────────────────────────────────────────────────────

    def _get_access_token(self, force_refresh=False, is_datastore=False):
        # Use datastore token if requested, otherwise fallback to master token
        target_refresh_token = self.datastore_refresh_token if is_datastore else self.refresh_token
        
        # Cache management
        cache_key = "_ds_token" if is_datastore else "_access_token"
        cached_token = getattr(self, cache_key, None)
        
        if cached_token and not force_refresh:
            return cached_token
        try:
            resp = requests.post(
                "https://accounts.zoho.in/oauth/v2/token",
                params={
                    "grant_type":    "refresh_token",
                    "client_id":     self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": target_refresh_token,
                },
                verify=False,
                timeout=30,
            )
            data  = resp.json()
            token = data.get("access_token")
            if not token:
                print(f"[Catalyst] Token fetch failed ({'DataStore' if is_datastore else 'Stratus'}): {data}")
                return None
            setattr(self, cache_key, token)
            return token
        except Exception as e:
            print(f"[Catalyst] Token fetch error: {e}")
            return None

    def _auth_headers(self, content_type="application/octet-stream", is_datastore=False, force_refresh=False):
        token = self._get_access_token(is_datastore=is_datastore, force_refresh=force_refresh)
        if not token:
            return None
        return {
            "Authorization": f"Zoho-oauthtoken {token}",
            "Content-Type":  content_type,
        }

    def _object_url(self, key):
        from urllib.parse import quote
        # Safe encoding that preserves folder structure but protects special filenames
        encoded_key = quote(key, safe='/') if key else ""
        return f"https://{self.bucket_name}-development.zohostratus.in/{encoded_key}"

    def get_base_url(self):
        """Returns the base URL for the current Stratus bucket."""
        return f"https://{self.bucket_name}-development.zohostratus.in"

    @property
    def enabled(self):
        token = self._get_access_token()
        if not token:
            print("[-] Catalyst not enabled — master token failed.")
            return False
        return True

    # ── Core upload ───────────────────────────────────────────────────────────

    def upload_object(self, key, content, options=None):
        """Upload object with retry logic for transient failures."""
        MAX_RETRIES = 3
        RETRY_DELAY = 2  # seconds
        
        try:
            full_key = f"{self.folder_prefix}{key}"
            url      = self._object_url(full_key)

            content_type = (options or {}).get("content_type", "application/octet-stream")
            
            # Normalise content to bytes
            if isinstance(content, str):
                body = content.encode("utf-8")
            elif hasattr(content, "read"):
                body = content.read()
            else:
                body = content

            # Retry loop for transient network failures
            for attempt in range(MAX_RETRIES):
                try:
                    headers = self._auth_headers(content_type)
                    if not headers:
                        print("[Stratus] Upload skipped — no access token.")
                        return None

                    resp = requests.put(url, headers=headers, data=body, verify=False, timeout=60)

                    if resp.status_code in (200, 201):
                        print(f"[Stratus] ✅ Uploaded: {full_key}")
                        return {"key": full_key, "url": url, "status": resp.status_code}

                    elif resp.status_code == 409:
                        # Key exists, delete first then re-upload (overwrite header unreliable in Zoho)
                        print(f"[Stratus] Key exists, deleting for overwrite: {full_key}")
                        del_headers = {"Authorization": f"Zoho-oauthtoken {self._get_access_token()}"}
                        requests.delete(url, headers=del_headers, verify=False, timeout=30)
                        resp2 = requests.put(url, headers=headers, data=body, verify=False, timeout=60)
                        if resp2.status_code in (200, 201):
                            print(f"[Stratus] ✅ Overwritten: {full_key}")
                            return {"key": full_key, "url": url, "status": resp2.status_code}
                        else:
                            print(f"[Stratus] ❌ Overwrite failed ({resp2.status_code}): {resp2.text[:300]}")
                            if attempt < MAX_RETRIES - 1:
                                print(f"[Stratus] Retrying in {RETRY_DELAY}s... (attempt {attempt+1}/{MAX_RETRIES})")
                                import time
                                time.sleep(RETRY_DELAY)
                                continue
                            return None
                    elif resp.status_code >= 500:
                        # Server error — retry
                        print(f"[Stratus] ❌ Server error ({resp.status_code}), retrying...")
                        if attempt < MAX_RETRIES - 1:
                            print(f"[Stratus] Retrying in {RETRY_DELAY}s... (attempt {attempt+1}/{MAX_RETRIES})")
                            import time
                            time.sleep(RETRY_DELAY)
                            continue
                        return None
                    else:
                        print(f"[Stratus] ❌ Upload failed ({resp.status_code}): {resp.text[:300]}")
                        return None
                        
                except (requests.Timeout, requests.ConnectionError, OSError) as e:
                    # Transient network error — retry
                    print(f"[Stratus] Network error on attempt {attempt+1}: {e}")
                    if attempt < MAX_RETRIES - 1:
                        print(f"[Stratus] Retrying in {RETRY_DELAY}s... (attempt {attempt+1}/{MAX_RETRIES})")
                        import time
                        time.sleep(RETRY_DELAY)
                        continue
                    else:
                        print(f"[Stratus] ❌ Upload failed after {MAX_RETRIES} attempts")
                        return None

        except Exception as e:
            print(f"[Stratus] upload_object error: {e}")
            return None

    # ── Convenience uploaders ─────────────────────────────────────────────────

    def upload_partner_data(self, data):
        """Uploads partner JSON data to Catalyst Stratus Bucket.
        
        In LOCAL MODE: Skips Catalyst upload entirely.
        In PRODUCTION: Uploads to Catalyst Stratus.
        """
        try:
            # Check if we're running locally — if so, skip Catalyst sync
            if self.is_local_mode():
                print(f"[*] LOCAL MODE: Skipping Catalyst sync for '{data.get('name')}'. Data saved locally only.", file=sys.stderr)
                return {"status": "local_only", "message": "Data saved locally (Catalyst sync disabled)"}
            
            partner_id = data.get("partner_id", "unknown")

            # FIX 1: Strip any existing "ext_" prefix to avoid "ext_ext_" double prefix
            partner_id_clean = str(partner_id).replace("ext_", "")
            object_path      = f"partners/ext_{partner_id_clean}.json"

            content = json.dumps(data, indent=2, ensure_ascii=False)
            result  = self.upload_object(object_path, content, {"content_type": "application/json"})
            if result:
                self.update_partners_index(data)
            return result
        except Exception as e:
            print(f"[Stratus] Partner upload error: {e}")

    def find_partner_by_name(self, name: str) -> dict | None:
        """
        Searches for an existing partner by name (case-insensitive).
        Returns the index entry if found, None if not.
        
        In LOCAL MODE: Searches local scraped_data/ files.
        In PRODUCTION: Searches cloud index.json.
        """
        name_lower = name.strip().lower()
        
        if self.is_local_mode():
            # Local search
            output_dir = os.path.join(os.getcwd(), "scraped_data")
            if os.path.exists(output_dir):
                for root, dirs, files in os.walk(output_dir):
                    for f in files:
                        if f.endswith(".json"):
                            try:
                                with open(os.path.join(root, f), "r", encoding="utf-8") as file:
                                    data = json.load(file)
                                if (data.get("name") or "").strip().lower() == name_lower:
                                    return {
                                        "id": data.get("partner_id"),
                                        "name": data.get("name"),
                                        "is_base": not bool(data.get("parent_company"))
                                    }
                            except: continue
            return None
        
        try:
            content = self.download_object("partners/index.json")
            if not content:
                return None
            index = json.loads(content)
            for entry in index:
                entry_name = (entry.get("name") or entry.get("display_name") or "").strip().lower()
                if entry_name == name_lower:
                    return entry
            return None
        except Exception as e:
            print(f"[Stratus] find_partner_by_name error: {e}")
            return None


    def save_partner(self, data: dict, parent_company: str = None) -> dict | None:
        """
        Smart save — the ONLY function you should call to store partner data.
        Replaces direct calls to upload_partner_data() when routing matters.

        In LOCAL MODE: Data is saved locally only (no Catalyst sync).
        In PRODUCTION: Data is synced to Catalyst Cloud.

        Rules:
          - parent_company NOT given at scrape time
            → ALWAYS create as new parent company
            → even if same name already exists in storage

          - parent_company WAS given at scrape time
            → find existing record by that parent name (cloud/local)
            → if found: UPDATE it (overwrite with new scrape data)
            → if not found: CREATE as new parent anyway

        Previous upload_partner_data() is preserved and still works for
        all existing code paths that call it directly.
        """
        try:
            # Check if running locally
            is_local = self.is_local_mode()
            
            if not parent_company:
                # No mapping given → always create as new parent
                data["parent_company"] = None
                data["is_base"]        = True
                if is_local:
                    print(f"[*] LOCAL MODE: No mapping given → storing locally: {data.get('name')}", file=sys.stderr)
                else:
                    print(f"[Stratus] No mapping given → creating as new parent: {data.get('name')}", file=sys.stderr)
                return self.upload_partner_data(data)

            # Mapping was given → find the parent record
            existing = self.find_partner_by_name(parent_company)

            if existing:
                # Found parent → Link this new scrape as a competitor/child
                if is_local:
                    print(f"[*] LOCAL MODE: Parent found '{parent_company}' → storing '{data.get('name')}' as child.", file=sys.stderr)
                else:
                    print(f"[Stratus] Parent found '{parent_company}' → Linking '{data.get('name')}' as child.", file=sys.stderr)
                # DO NOT overwrite partner_id here! Keep the unique ID of the new scrape
                data["parent_company"] = parent_company
                data["is_base"]        = False
                result = self.upload_partner_data(data)

                # --- NEW: Create Combined Record (Base + Competitor) ---
                if result:
                    try:
                        if is_local:
                            # In local mode, find the base data from local files
                            base_id = existing.get("id")
                            if base_id:
                                import glob
                                pattern = os.path.join("scraped_data", "**", f"*_{base_id}.json")
                                matches = glob.glob(pattern, recursive=True)
                                if matches:
                                    with open(matches[0], "r", encoding="utf-8") as f:
                                        base_data = json.load(f)
                                        self.save_combined_record(base_data, data)
                        else:
                            # In cloud mode, download from Stratus
                            base_file_key = existing.get("file_key")
                            if base_file_key:
                                base_content = self.download_object(base_file_key)
                                if base_content:
                                    base_data = json.loads(base_content)
                                    self.save_combined_record(base_data, data)
                    except Exception as e:
                        print(f"[Stratus] Combined record creation failed: {e}")


                return result
            else:
                # Mapping given but parent not found → create as new parent anyway
                if is_local:
                    print(f"[*] LOCAL MODE: Mapping '{parent_company}' not found → storing as new parent.", file=sys.stderr)
                else:
                    print(f"[Stratus] Mapping '{parent_company}' not found in storage → creating as new parent.", file=sys.stderr)
                data["parent_company"] = None
                data["is_base"]        = True
                return self.upload_partner_data(data)

        except Exception as e:
            print(f"[Stratus] save_partner error: {e}")
            return None

    def upload_report(self, file_path, company_name=None):
        """Uploads a PDF report to Catalyst Stratus Bucket using streaming.
        Updates reports/index.json so the dashboard can find it easily.
        """
        try:
            if self.is_local_mode():
                print(f"[*] LOCAL MODE: Report saved locally. Catalyst upload skipped: {os.path.basename(file_path)}", file=sys.stderr)
                return {"status": "local_only", "message": "Report saved locally"}
            
            if not os.path.exists(file_path):
                print(f"[Stratus] Report upload failed: File not found at {file_path}")
                return None
                
            filename    = os.path.basename(file_path)
            object_path = f"reports/{filename}"
            
            with open(file_path, "rb") as f:
                result = self.upload_object(object_path, f, {"content_type": "application/pdf"})
            
            if result:
                print(f"[Stratus] Report synced to bucket: {filename}")
                
                # Derive a clean display name for the index
                # Priority: 1. Passed company_name, 2. Filename part before _Analysis or _
                display_name = company_name
                if not display_name:
                    display_name = filename.split('_Analysis')[0].split('_')[0]
                
                # Update the index so the dashboard can find it instantly
                self.update_reports_index({
                    "company_name": display_name,
                    "file_name": filename,
                    "mtime": int(time.time())
                })
            
            return result
        except Exception as e:
            print(f"[Stratus] Report upload error: {e}")

    def update_reports_index(self, report_data):
        """
        Maintains reports/index.json — a master list of all generated reports.
        Helps the dashboard find reports without scanning the whole bucket.
        """
        try:
            # 1. Download existing index
            existing = []
            content  = self.download_object("reports/index.json")
            if content:
                try:
                    existing = json.loads(content)
                except:
                    existing = []

            # 2. Add new entry (always add to the beginning so newest is first)
            existing.insert(0, report_data)
            
            # 3. Limit index size to last 100 reports for performance
            existing = existing[:100]

            # 4. Upload updated index
            self.upload_object(
                "reports/index.json",
                json.dumps(existing, indent=2),
                {"content_type": "application/json"}
            )
            print(f"[Stratus] ✅ Reports Index updated for: {report_data.get('company_name')}")
            return True
        except Exception as e:
            print(f"[Stratus] update_reports_index error: {e}")
            return False

    # ── Directory sync ────────────────────────────────────────────────────────

    def sync_directory(self, local_dir, bucket_prefix=""):
        if not os.path.exists(local_dir):
            print(f"[Stratus] Sync failed: Local directory '{local_dir}' not found.")
            return
        print(f"[Stratus] Starting recursive sync of '{local_dir}' to '{bucket_prefix or '/'}'...")
        success_count = 0
        error_count   = 0
        for root, dirs, files in os.walk(local_dir):
            for filename in files:
                local_path = os.path.join(root, filename)
                rel_path   = os.path.relpath(local_path, local_dir)
                bucket_key = (
                    f"{bucket_prefix.rstrip('/')}/{rel_path.replace(os.sep, '/')}"
                    if bucket_prefix else rel_path.replace(os.sep, "/")
                )
                options = {}
                if filename.endswith(".json"):  options["content_type"] = "application/json"
                elif filename.endswith(".pdf"): options["content_type"] = "application/pdf"
                elif filename.endswith(".txt"): options["content_type"] = "text/plain"
                try:
                    with open(local_path, "rb") as f:
                        self.upload_object(bucket_key, f, options)
                    success_count += 1
                except Exception as e:
                    print(f"[-] Failed to sync {rel_path}: {e}")
                    error_count += 1
        print(f"[Stratus] Sync complete. Success: {success_count}, Errors: {error_count}")
        return {"success": success_count, "errors": error_count}

    # ── Download ──────────────────────────────────────────────────────────────

    def download_object(self, key, local_path=None):
        try:
            # Simplest possible path resolution to avoid double-prefixing
            url     = self._object_url(key)
            headers = self._auth_headers()
            if not headers:
                return None
            resp = requests.get(url, headers=headers, verify=False, timeout=60)
            if resp.status_code != 200:
                print(f"[Stratus] Download failed ({resp.status_code}): {resp.text[:200]}")
                return None
            content = resp.content
            if local_path:
                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                with open(local_path, "wb") as f:
                    f.write(content)
                print(f"[Stratus] Downloaded and saved to: {local_path}")
            return content
        except Exception as e:
            print(f"[Stratus] download_object error: {e}")
            return None

    def sync_from_cloud(self, bucket_prefix, local_dir):
        try:
            objects = self._list_objects(prefix=bucket_prefix)
            print(f"[Stratus] Starting sync FROM cloud: '{bucket_prefix}' -> '{local_dir}'...")
            success_count = 0
            error_count   = 0
            for obj in objects:
                bucket_key = obj.get("name") or obj.get("key", "")
                rel_path   = bucket_key.replace(bucket_prefix.rstrip("/"), "").lstrip("/")
                local_path = os.path.join(local_dir, rel_path.replace("/", os.sep))
                try:
                    self.download_object(bucket_key, local_path)
                    success_count += 1
                except Exception as e:
                    print(f"[-] Failed to download {bucket_key}: {e}")
                    error_count += 1
            print(f"[Stratus] Cloud-to-Local sync complete. Success: {success_count}, Errors: {error_count}")
            return {"success": success_count, "errors": error_count}
        except Exception as e:
            print(f"[Stratus] sync_from_cloud error: {e}")
            return None

    # ── List helpers ──────────────────────────────────────────────────────────

    def _list_objects(self, prefix=""):
        try:
            project_id = os.getenv("PROJECT_ID", "39634000000012090")
            token      = self._get_access_token()
            url        = (
                f"https://api.catalyst.zoho.in/baas/v1/project/{project_id}"
                f"/stratus/bucket/{self.bucket_name}/objects"
            )
            params  = {"prefix": prefix} if prefix else {}
            headers = {"Authorization": f"Zoho-oauthtoken {token}"}
            resp    = requests.get(url, headers=headers, params=params, verify=False, timeout=30)
            if resp.status_code == 200:
                return resp.json().get("data", {}).get("objects", [])
            return []
        except Exception as e:
            print(f"[Stratus] list_objects error: {e}")
            return []

    # ── Index management ──────────────────────────────────────────────────────

    def update_partners_index(self, partner_data):
        """
        Maintains partners/index.json — master list of all partners.
        Called automatically after every upload_partner_data().
        """
        try:
            # 1. Download existing index
            existing = []
            content  = self.download_object("partners/index.json")
            if content:
                try:
                    existing = json.loads(content)
                except Exception:
                    existing = []

            # 2. FIX 3: Safely extract name — never use a URL as name
            partner_id = partner_data.get("partner_id") or partner_data.get("id", "")
            name       = partner_data.get("name") or partner_data.get("company_name") or "Unknown"
            if name.startswith("http") or name.startswith("www"):
                name = partner_data.get("display_name") or partner_data.get("title") or "Unknown"

            parent = (
                partner_data.get("parent_company")
                or partner_data.get("relationship", {}).get("parent_company")
            )

            # FIX 1: Clean partner_id for file_key
            partner_id_clean = str(partner_id).replace("ext_", "")

            entry = {
                "partner_id":     partner_id,
                "name":           name,
                "display_name":   partner_data.get("display_name", name),
                "parent_company": parent,
                "is_base":        not bool(parent),
                "file_key":       f"partners/ext_{partner_id_clean}.json",
            }

            # 3. Upsert
            updated = False
            for i, e in enumerate(existing):
                if e.get("partner_id") == partner_id:
                    existing[i] = entry
                    updated = True
                    break
            if not updated:
                existing.append(entry)

            # 4. Upload index (409 handled by delete+reupload in upload_object)
            self.upload_object(
                "partners/index.json",
                json.dumps(existing, indent=2, ensure_ascii=False),
                {"content_type": "application/json"}
            )
            print(f"[Stratus] ✅ Index updated with: {name} (is_base: {not bool(parent)})")
            return existing

        except Exception as e:
            print(f"[Stratus] update_partners_index error: {e}")
            return []

    def list_partners(self):
        """
        Lists all partner records from bucket via index.json.
        Fast — reads index first, then fetches each partner file.
        """
        try:
            content = self.download_object("partners/index.json")
            if not content:
                print("[Stratus] index.json not found, no partners to load.")
                return []

            index = json.loads(content)
            if not index:
                return []

            print(f"[Stratus] Loaded {len(index)} partners from index.json")
            partners = []
            for entry in index:
                partner_id_clean = str(entry.get("partner_id", "")).replace("ext_", "")
                file_key         = entry.get("file_key") or f"partners/ext_{partner_id_clean}.json"
                try:
                    file_content = self.download_object(file_key)
                    if file_content:
                        partners.append(json.loads(file_content))
                    else:
                        partners.append(entry)
                except Exception:
                    partners.append(entry)
            return partners

        except Exception as e:
            print(f"[Stratus] list_partners error: {e}")
            return []

    def list_reports(self):
        """
        Lists all PDF reports from the Stratus bucket.
        Uses reports/index.json for speed, falls back to folder listing if missing.
        """
        try:
            # 1. Try to get from the reports index first (Preferred method)
            index_content = self.download_object("reports/index.json")
            if index_content:
                try:
                    index_data = json.loads(index_content)
                    print(f"[Stratus] Loaded {len(index_data)} reports from reports/index.json")
                    return index_data
                except:
                    pass

            # 2. Fallback: Manually list the reports folder
            objs = self._list_objects(prefix="reports/")
            result = []

            for obj in objs:
                full_key = obj.get("key") or obj.get("object_name") or ""
                if not full_key or full_key.endswith("/"):
                    continue

                # Clean the filename for display
                fname = full_key.replace("reports/", "").strip("/")
                if fname and fname.endswith(".pdf"):
                    mtime = obj.get("last_modified", 0) or obj.get("mtime", 0)
                    result.append({"file_name": fname, "mtime": mtime})

            print(f"[Stratus] list_reports found {len(result)} reports")
            return result

        except Exception as e:
            print(f"[Stratus] list_reports error: {e}")
            return []


    # ── Delete ────────────────────────────────────────────────────────────────

    def delete_partner(self, partner_id):
        """
        Deletes a partner file from bucket AND removes from index.json.
        Always use this instead of deleting from Catalyst console directly.
        """
        try:
            partner_id_clean = str(partner_id).replace("ext_", "")
            file_key         = f"partners/ext_{partner_id_clean}.json"

            # 1. Delete the partner file
            url     = self._object_url(file_key)
            headers = {"Authorization": f"Zoho-oauthtoken {self._get_access_token()}"}
            resp    = requests.delete(url, headers=headers, verify=False, timeout=30)
            print(f"[Stratus] Deleted {file_key}: {resp.status_code}")

            # 2. Remove from index.json
            content = self.download_object("partners/index.json")
            if content:
                index   = json.loads(content)
                updated = [e for e in index if e.get("partner_id") != partner_id]
                self.upload_object(
                    "partners/index.json",
                    json.dumps(updated, indent=2, ensure_ascii=False),
                    {"content_type": "application/json"}
                )
                print(f"[Stratus] ✅ Removed from index. {len(updated)} partners remaining.")
            return True
        except Exception as e:
            print(f"[Stratus] delete_partner error: {e}")
            return False

    def delete_files(self, path, file_names):
        """Deletes one or more files from Stratus by path."""
        try:
            if not isinstance(file_names, list):
                file_names = [file_names]
            token   = self._get_access_token()
            headers = {"Authorization": f"Zoho-oauthtoken {token}"}
            for name in file_names:
                key  = f"{path}/{name}" if path else name
                url  = self._object_url(key)
                resp = requests.delete(url, headers=headers, verify=False, timeout=30)
                print(f"[Stratus] Delete {key}: {resp.status_code}")
        except Exception as e:
            print(f"[Stratus] Delete error: {e}")

    def save_combined_record(self, base_data: dict, competitor_data: dict):
        """
        Creates/Updates a consolidated JSON file for a base company and ALL its competitors.
        Uses a specific unique hashed ID that does not reveal the base ID.
        """
        try:
            import hashlib
            base_id = base_data.get("partner_id") or base_data.get("id", "unknown")
            comp_id = competitor_data.get("partner_id") or competitor_data.get("id", "unknown")
            
            # Generate a specific unique hash-based ID (CID_ + 12 chars)
            base_id_clean = str(base_id).replace("ext_", "")
            unique_hash = hashlib.md5(base_id_clean.encode()).hexdigest()[:12]
            combined_id = f"CID_{unique_hash}"
            
            # 1. Fetch existing record if any
            existing_record = {}
            if self.is_local_mode():
                local_dir = os.path.join(os.getcwd(), "companies data folder")
                os.makedirs(local_dir, exist_ok=True)
                local_path = os.path.join(local_dir, f"{combined_id}.json")
                if os.path.exists(local_path):
                    with open(local_path, "r", encoding="utf-8") as f:
                        try: existing_record = json.load(f)
                        except: existing_record = {}
            else:
                try:
                    content = self.download_object(f"combined_records/{combined_id}.json")
                    if content: existing_record = json.loads(content)
                except: existing_record = {}
            
            # 2. Prepare or Update the record
            if not existing_record or "competitors" not in existing_record:
                existing_record = {
                    "combined_id":  combined_id,
                    "base_company": {
                        "partner_id": base_id,
                        "name":       base_data.get("name", "Unknown")
                    },
                    "competitors": [],
                    "last_updated": time.strftime("%Y-%m-%d %H:%M:%S")
                }
            
            # Prepare competitor snippet
            comp_snippet = {
                "partner_id":   comp_id,
                "name":         competitor_data.get("name", "Unknown"),
                "relationship": competitor_data.get("relationship", {})
            }

            # 3. Add or Update competitor in the list
            competitors = existing_record.get("competitors", [])
            found = False
            for i, existing_comp in enumerate(competitors):
                if existing_comp.get("partner_id") == comp_id:
                    competitors[i] = comp_snippet
                    found = True
                    break
            
            if not found:
                competitors.append(comp_snippet)
            
            existing_record["competitors"] = competitors
            existing_record["last_updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
            content = json.dumps(existing_record, indent=2, ensure_ascii=False)
            
            # 4. Save consolidated record
            if self.is_local_mode():
                local_path = os.path.join(os.getcwd(), "companies data folder", f"{combined_id}.json")
                with open(local_path, "w", encoding="utf-8") as f:
                    f.write(content)
                print(f"[*] LOCAL MODE: Consolidated record updated with ID '{combined_id}': {local_path}")
                return {"status": "local_only", "key": combined_id}
            else:
                object_path = f"combined_records/{combined_id}.json"
                result = self.upload_object(object_path, content, {"content_type": "application/json"})
                return {"status": "synced", "key": combined_id} if result else None
        except Exception as e:
            print(f"[Stratus] save_combined_record error: {e}")
            return None

    def build_index_from_bucket(self):
        """
        Scans all JSON files in partners/ folder in Stratus bucket
        and rebuilds the partners/index.json file.
        Call this once from /rebuild-index route to fix missing index.
        """
        try:
            token = self._get_access_token()
            if not token:
                return {"success": False, "error": "No token"}

            base_url = f"https://{self.bucket_name}-development.zohostratus.in"
            list_url = f"{base_url}/?prefix=partners/"
            headers  = {"Authorization": f"Zoho-oauthtoken {token}"}

            resp = requests.get(list_url, headers=headers, verify=False, timeout=30)
            if resp.status_code != 200:
                return {"success": False, "error": f"List failed: {resp.status_code}"}

            import re
            keys = re.findall(r"<Key>(.*?)</Key>", resp.text)
            partner_keys = [k for k in keys if k.endswith(".json") and "index" not in k]

            index = []
            for key in partner_keys:
                try:
                    content = self.download_object(key)
                    if content:
                        data = json.loads(content)
                        partner_id = data.get("partner_id", key.split("/")[-1].replace(".json",""))
                        index.append({
                            "partner_id": partner_id,
                            "name":       data.get("name", "Unknown"),
                            "file_key":   key
                        })
                except:
                    pass

            self.upload_object("partners/index.json", json.dumps(index, indent=2))
            print(f"[Stratus] ✅ Rebuilt index.json with {len(index)} partners")
            return {"success": True, "count": len(index), "partners": [i["name"] for i in index]}

        except Exception as e:
            print(f"[Stratus] build_index error: {e}")
            return {"success": False, "error": str(e)}

    def insert_row(self, table_name, row_data):
        """
        Inserts a single row into a Catalyst Data Store table using Direct API.
        Automatically handles token refresh if expired.
        """
        try:
            # 1. Get Project ID
            project_id = "39634000000012090"
            
            # 2. Get Auth Headers (Attempt 1)
            headers = self._auth_headers("application/json", is_datastore=True)
            if not headers:
                print("[-] DataStore: Auth failed (No token).")
                return False
            
            # 3. Construct URL
            url = f"https://api.catalyst.zoho.in/baas/v1/project/{project_id}/table/{table_name}/row"
            
            # 4. Execute Request
            resp = requests.post(url, headers=headers, json=[{"row_data": row_data}], verify=False, timeout=30)
            
            # 5. Handle Token Expiration (401)
            if resp.status_code == 401:
                print("[DataStore] 🔄 Token expired, refreshing...")
                # Force refresh the token by passing force_refresh=True
                new_headers = self._auth_headers("application/json", is_datastore=True, force_refresh=True)
                # Retry
                resp = requests.post(
                    url, 
                    headers=new_headers, 
                    json=[{"row_data": row_data}],  # ← wrap in list
                    verify=False, 
                    timeout=30
                    )
            
            if resp.status_code in (200, 201):
                print(f"[DataStore] ✅ Row inserted into {table_name}")
                return True
            else:
                print(f"[DataStore] ❌ API Error ({resp.status_code}): {resp.text[:300]}")
                return False
                
        except Exception as e:
            print(f"[DataStore] ❌ Exception: {e}")
            return False

            
    def insert_row_always(self, table_name, row_data):
        """
        Inserts to Catalyst DataStore via our dedicated Catalyst Function bridge.
        This uses the SDK inside the function for maximum reliability.
        """
        print(f"[*] [Function Bridge] Attempting sync for: {row_data.get('base_company_name')}")
        
        # We call our newly created AdvancedIO function endpoint
        url = f"{self.function_base_url}/record"
        
        try:
            # We still need a token to call the function if it's protected, 
            # but usually AdvancedIO functions handle their own auth or are public-facing with secret keys.
            # For now, we'll send it as a clean POST request.
            headers = {"Content-Type": "application/json"}
            
            # The function expects the raw row_data keys (record_id, base_company_name, etc.)
            resp = requests.post(url, headers=headers, json=row_data, verify=False, timeout=60)
            
            if resp.status_code in (200, 201):
                result = resp.json()
                print(f"[Function Bridge] ✅ Success: {result.get('message')}")
                return True
            else:
                print(f"[Function Bridge] ❌ Error ({resp.status_code}): {resp.text[:500]}")
                # Fallback to direct insertion if function fails (for redundancy)
                print("[Function Bridge] 🔄 Falling back to direct DataStore API...")
                return self.insert_row_direct_fallback(table_name, row_data)

        except Exception as e:
            print(f"[Function Bridge] ❌ Connection Exception: {e}")
            return self.insert_row_direct_fallback(table_name, row_data)

    def insert_row_direct_fallback(self, table_name, row_data):
        """
        The original direct DataStore API insertion logic (as a backup).
        """
        project_id = "39634000000012090"
        payload = [{"row_data": row_data}]
        try:
            headers = self._auth_headers("application/json", is_datastore=True)
            if not headers: return False
            url = f"https://api.catalyst.zoho.in/baas/v1/project/{project_id}/table/{table_name}/row"
            resp = requests.post(url, headers=headers, json=payload, verify=False, timeout=30)
            return resp.status_code in (200, 201)
        except:
            return False





# ─────────────────────────────────────────────────────────────────────────────
# Singleton instance
# ─────────────────────────────────────────────────────────────────────────────
catalyst_client = CatalystClient()


# ─────────────────────────────────────────────────────────────────────────────
# Factory
# ─────────────────────────────────────────────────────────────────────────────
def get_catalyst_client(app=None):
    return CatalystClient()