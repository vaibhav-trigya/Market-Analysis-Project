import sys
import os
sys.path.append(os.getcwd())
from storage import save_report_as_pdf

# Mock data
content = """
### ACTIONABLE STRATEGIC RECOMMENDATIONS
- [Content Strategy: Develop a robust content strategy focusing on blogs and case studies to build trust.] -> [Enhance thought leadership and client trust].
- [Social Media: Increase social media engagement across LinkedIn, Instagram, and Facebook.] -> [Boost brand visibility and client interaction].
- [Influencer Collaboration: Collaborate with industry influencers to co-create content.] -> [Strengthen market authority and reach new audiences].
- [Webinars: Implement a regular webinar series focused on Zoho solutions.] -> [Position as a thought leader and engage potential clients].
- [Success Stories: Leverage client success stories in marketing materials.] -> [Demonstrate expertise and build credibility].
"""

partners_data = [
    {"name": "Trigya Innovations", "blogs": [1,2], "case_studies": [1], "customer_stories": []},
    {"name": "Competitor 1", "blogs": [1], "case_studies": [1], "customer_stories": [1]},
]

save_report_as_pdf(content, "Test_Alignment_Fix.pdf", partners_data=partners_data)
print("PDF Generated: trigya report/Test_Alignment_Fix.pdf")
