"""API dependency injection — keeps routes thin."""

from services.billing_service.stripe_billing import BillingService
from services.dashboard_service import DashboardService
from services.scanner_service.pipeline import ScannerPipeline
from services.scanner_service.scanner_service import ScannerService

_pipeline = ScannerPipeline()
_scanner = ScannerService(_pipeline)
_dashboard = DashboardService(_scanner)
_billing = BillingService()


def get_pipeline() -> ScannerPipeline:
    return _pipeline


def get_scanner_service() -> ScannerService:
    return _scanner


def get_dashboard_service() -> DashboardService:
    return _dashboard


def get_billing_service() -> BillingService:
    return _billing
