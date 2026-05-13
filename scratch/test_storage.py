import json
import os
from storage import generate_report

dummy_data = {
    "partners": [
        {
            "name": "Trigya Innovations",
            "scores": {
                "technical_depth": 80,
                "customer_success": 70,
                "market_authority": 40
            }
        },
        {
            "name": "Partner A",
            "scores": {
                "technical_depth": 50,
                "customer_success": 60,
                "market_authority": 30
            }
        }
    ],
    "executive_summary": "Test Summary",
    "cohort": "Test Cohort",
    "performance_index_context": "Test Context",
    "interpretation": "Test Interpretation",
    "leaders": [{"name": "Leader 1", "insight": "Insight 1"}],
    "gap": "Test Gap",
    "recommendations": [{"title": "Rec 1", "description": "Desc 1", "impact": "Impact 1"}],
    "path": "Test Path",
    "radar_context": "Test Radar",
    "gap_metrics": {"Metric 1": -10, "Metric 2": 20},
    "authority_distribution_context": "Test Authority",
    "scores": {"Metric 1": 80, "Metric 2": 70},
    "final_insight": "Test Final"
}

try:
    path = generate_report(dummy_data, "test_report.pdf")
    print(f"Report generated at: {path}")
except Exception as e:
    import traceback
    traceback.print_exc()
