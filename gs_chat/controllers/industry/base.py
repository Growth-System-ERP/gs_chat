"""Base class for industry-specific implementations"""

import frappe
from abc import ABC, abstractmethod

class BaseIndustry(ABC):
    """Base class for all industry implementations"""
    
    def __init__(self):
        self.industry_name = None
        self.priority_doctypes = []
        self.search_synonyms = {}
        self.custom_metrics = {}
        
    @abstractmethod
    def get_priority_doctypes(self):
        """Return list of priority doctypes for this industry"""
        pass
    
    @abstractmethod
    def get_search_synonyms(self):
        """Return industry-specific search synonyms"""
        pass
    
    @abstractmethod
    def preprocess_query(self, query):
        """Preprocess query with industry-specific enhancements"""
        pass
    
    @abstractmethod
    def get_custom_metrics(self):
        """Calculate and return industry-specific metrics"""
        pass
    
    @abstractmethod
    def get_schema_filters(self):
        """Return filters for loading relevant doctypes"""
        pass
    
    def get_document_metadata(self, doctype_name):
        """Return additional metadata for documents"""
        return {
            "industry": self.industry_name,
            "is_priority": doctype_name in self.priority_doctypes
        }