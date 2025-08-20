"""Industry module loader and factory"""

import frappe
from .base import BaseIndustry
from .nbfc import NBFCIndustry

# Industry mapping
INDUSTRY_CLASSES = {
    "NBFC": NBFCIndustry,
    # Future industries
    # "FMCG": FMCGIndustry,
    # "GMRT": GMRTIndustry,
    # "FRNR": FRNRIndustry,
}

def get_industry_handler(industry_type=None):
    """
    Factory method to get the appropriate industry handler
    
    Args:
        industry_type: Industry type from settings. If None, fetches from settings
        
    Returns:
        Instance of appropriate industry class or None
    """
    if not industry_type:
        # Try to fetch from settings (adjust doctype name as per your settings)
        try:
            settings = frappe.get_single("Chatbot Settings")
            industry_type = settings.get("industry")
        except:
            frappe.log_error("Chatbot Settings not found or industry field missing")
            return None
    
    if industry_type in INDUSTRY_CLASSES:
        return INDUSTRY_CLASSES[industry_type]()
    else:
        frappe.log_error(f"Industry type {industry_type} not implemented")
        return None

def get_active_industry():
    """Get the currently active industry from settings"""
    try:
        settings = frappe.get_single("Chatbot Settings")
        return settings.get("industry", "NBFC")  # Default to NBFC
    except:
        return "NBFC"

# Export for easy access
__all__ = ['get_industry_handler', 'get_active_industry', 'BaseIndustry']
