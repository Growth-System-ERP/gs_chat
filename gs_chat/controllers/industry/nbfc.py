"""NBFC industry-specific implementation"""

import frappe
import re
from .base import BaseIndustry

class NBFCIndustry(BaseIndustry):
    """NBFC-specific implementation for chatbot"""

    def __init__(self):
        super().__init__()
        self.industry_name = "NBFC"
        self.priority_doctypes = self.get_priority_doctypes()
        self.search_synonyms = self.get_search_synonyms()

    def get_priority_doctypes(self):
        """Return NBFC-specific priority doctypes"""
        return [
            "Loan",
            "Loan Application",
            "Loan Repayment Schedule",
            "Loan Interest Accrual",
            "Loan Repayment",
            "Loan Disbursement",
            "Loan Security",
            "Loan Security Pledge",
            "Loan Security Unpledge",
            "Loan Security Shortfall",
            "Loan Security Type",
            "Loan Security Price"
            "Loan Write Off",
            "Loan Closure",
            "Loan Restructure",
            "Payment Entry",
            "Proposed Pledge",
            "Sales Invoice",
            "Sales Order",
            "Journal Entry",
            "Customer",
            "Loan Type",
            "Loan Product",
            "Loan Partner",
            "Sanctioning Authority"
        ]

    def get_search_synonyms(self):
        """Return NBFC-specific search synonyms"""
        return {
            "balance": ["outstanding", "principal", "amount due", "remaining amount", "pending amount"],
            "missed": ["overdue", "delayed", "pending", "unpaid", "defaulted", "dpd", "days past due"],
            "accrual": ["interest accrued", "accumulated interest", "interest calculation", "interest due"],
            "emi": ["installment", "repayment", "monthly payment", "equated monthly installment"],
            "npa": ["non performing asset", "default", "bad loan", "stressed asset", "substandard asset"],
            "disbursement": ["loan disbursal", "amount disbursed", "sanctioned amount", "loan amount"],
            "foreclosure": ["loan closure", "early settlement", "prepayment", "pre-closure"],
            "moratorium": ["payment holiday", "emi holiday", "payment deferment", "grace period"],
            "los": ["loan origination system", "loan application", "loan processing"],
            "lms": ["loan management system", "loan servicing"],
            "pd": ["probability of default", "default probability"],
            "lgd": ["loss given default", "recovery rate"],
            "ead": ["exposure at default", "outstanding at default"],
            "collection": ["recovery", "collection efficiency", "bucket movement"],
            "provision": ["provisioning", "ecl", "expected credit loss"],
            "restructure": ["loan restructuring", "rescheduling", "recast"],
            "securitization": ["loan sale", "portfolio sale", "asset sale"],
            "co-lending": ["co-origination", "partnership lending", "nbfc bank partnership"]
        }

    def preprocess_query(self, query):
        """Enhanced query preprocessing for NBFC"""
        enhanced_query = query
        query_lower = query.lower()

        # Add synonyms
        for term, synonyms in self.search_synonyms.items():
            if term in query_lower:
                enhanced_query += f" {' '.join(synonyms)}"

        # Detect loan ID patterns (customize based on your format)
        loan_patterns = [
            r'(LOAN-\d+)',
            r'(LN\d+)',
            r'(ACC-\d+)',
            r'(LAP-\d+)',  # Loan application
            r'(\d{10,12})'  # Account numbers
        ]

        for pattern in loan_patterns:
            if re.search(pattern, query, re.IGNORECASE):
                enhanced_query += " loan_id account_number loan_account loan_reference"
                break

        # Detect date-related queries
        date_keywords = ["today", "yesterday", "this month", "last month", "this week",
                        "overdue since", "due date", "payment date"]
        if any(keyword in query_lower for keyword in date_keywords):
            enhanced_query += " date payment_date due_date posting_date"

        # Detect amount-related queries
        amount_keywords = ["amount", "total", "sum", "balance", "outstanding", "paid", "collection"]
        if any(keyword in query_lower for keyword in amount_keywords):
            enhanced_query += " amount total_amount outstanding_amount paid_amount"

        return enhanced_query

    def get_custom_metrics(self):
        """Calculate NBFC-specific metrics"""
        metrics = {}

        try:
            # Portfolio metrics
            metrics["portfolio_outstanding"] = frappe.db.sql("""
                SELECT
                    COUNT(*) as total_loans,
                    COALESCE(SUM(total_payment - total_amount_paid), 0) as total_outstanding,
                    COALESCE(AVG(rate_of_interest), 0) as avg_interest_rate
                FROM `tabLoan`
                WHERE status = 'Disbursed' AND docstatus = 1
            """, as_dict=True)[0]

            # Collection efficiency
            metrics["collection_efficiency"] = frappe.db.sql("""
                SELECT
                    COALESCE(SUM(CASE WHEN paid = 1 THEN total_payment ELSE 0 END), 0) as collected,
                    COALESCE(SUM(total_payment), 0) as total_due
                FROM `tabLoan Repayment Schedule`
                WHERE payment_date <= CURDATE() AND docstatus = 1
            """, as_dict=True)[0]

            if metrics["collection_efficiency"]["total_due"] > 0:
                metrics["collection_efficiency"]["efficiency_percent"] = (
                    metrics["collection_efficiency"]["collected"] /
                    metrics["collection_efficiency"]["total_due"] * 100
                )

            # DPD Buckets (Days Past Due)
            metrics["dpd_buckets"] = frappe.db.sql("""
                SELECT
                    CASE
                        WHEN DATEDIFF(CURDATE(), payment_date) = 0 THEN 'Current'
                        WHEN DATEDIFF(CURDATE(), payment_date) BETWEEN 1 AND 30 THEN 'DPD 1-30'
                        WHEN DATEDIFF(CURDATE(), payment_date) BETWEEN 31 AND 60 THEN 'DPD 31-60'
                        WHEN DATEDIFF(CURDATE(), payment_date) BETWEEN 61 AND 90 THEN 'DPD 61-90'
                        ELSE 'DPD 90+'
                    END as bucket,
                    COUNT(DISTINCT loan) as loan_count,
                    COALESCE(SUM(total_payment), 0) as amount
                FROM `tabLoan Repayment Schedule`
                WHERE paid = 0 AND docstatus = 1
                GROUP BY bucket
            """, as_dict=True)

            # NPA Statistics
            metrics["npa_stats"] = frappe.db.sql("""
                SELECT
                    COUNT(DISTINCT loan) as npa_accounts,
                    COALESCE(SUM(total_payment), 0) as npa_amount
                FROM `tabLoan Repayment Schedule`
                WHERE payment_date < DATE_SUB(CURDATE(), INTERVAL 90 DAY)
                AND paid = 0 AND docstatus = 1
            """, as_dict=True)[0]

            # Today's business
            metrics["todays_business"] = frappe.db.sql("""
                SELECT
                    COALESCE(SUM(ld.disbursed_amount), 0) as disbursed_today,
                    COALESCE(SUM(lr.amount_paid), 0) as collected_today,
                    COUNT(DISTINCT ld.loan) as loans_disbursed,
                    COUNT(DISTINCT lr.loan) as loans_collected
                FROM `tabLoan Disbursement` ld
                LEFT JOIN `tabLoan Repayment` lr ON DATE(lr.posting_date) = CURDATE()
                WHERE DATE(ld.disbursement_date) = CURDATE()
                AND ld.docstatus = 1
            """, as_dict=True)[0]

        except Exception as e:
            frappe.log_error(f"Error calculating NBFC metrics: {str(e)}", "NBFC Metrics")

        return metrics

    def get_schema_filters(self):
        """Return filters for loading NBFC-relevant doctypes"""
        return [
            # Core loan doctypes
            {"name": ["in", self.priority_doctypes]},
            # Custom doctypes with loan/payment/collection in name
            {"custom": 1, "name": ["like", "%loan%"]},
            {"custom": 1, "name": ["like", "%payment%"]},
            {"custom": 1, "name": ["like", "%collection%"]},
            {"custom": 1, "name": ["like", "%recovery%"]},
            {"custom": 1, "name": ["like", "%credit%"]}
        ]

    def get_document_metadata(self, doctype_name):
        """Enhanced metadata for NBFC documents"""
        metadata = super().get_document_metadata(doctype_name)

        # Add NBFC-specific metadata
        metadata.update({
            "is_financial": True,
            "is_loan_related": "loan" in doctype_name.lower(),
            "is_payment_related": "payment" in doctype_name.lower() or "repayment" in doctype_name.lower(),
            "is_collection_related": "collection" in doctype_name.lower() or "recovery" in doctype_name.lower()
        })

        return metadata

    def get_custom_prompts(self):
        """Return NBFC-specific prompt templates"""
        return {
            "loan_summary": """
                Provide a summary of loan {loan_id} including:
                - Current outstanding amount
                - Next EMI due date
                - Overdue status if any
                - Interest rate and tenure
            """,
            "collection_status": """
                Show collection status for {period} including:
                - Total amount due
                - Amount collected
                - Collection efficiency percentage
                - Number of accounts
            """,
            "npa_report": """
                Generate NPA report showing:
                - Total NPA accounts
                - NPA amount
                - DPD bucket distribution
                - Top defaulters
            """
        }
