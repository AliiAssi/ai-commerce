from __future__ import annotations

from app.application.events.bus import EventBus
from app.application.events.handlers import register_handlers
from app.application.iservices.iadmin_service import IAdminService
from app.application.iservices.iai_gateway import IAIGateway
from app.application.iservices.iauth_service import IAuthService
from app.application.iservices.icart_service import ICartService
from app.application.iservices.icatalog_search_service import ICatalogSearchService
from app.application.iservices.iorder_service import IOrderService
from app.application.iservices.iproduct_service import IProductService
from app.application.iservices.ireview_service import IReviewService
from app.application.services.admin_service import AdminService
from app.application.services.ai_gateway import AIGateway
from app.application.services.auth_service import AuthService
from app.application.services.cart_service import CartService
from app.application.services.catalog_search_service import CatalogSearchService
from app.application.services.order_service import OrderService
from app.application.services.product_service import ProductService
from app.application.services.review_service import ReviewService
from app.core.config import Settings
from app.core.container import Container, ScopeFactory
from app.infrastructure.database.session import create_engine_and_sessionmaker
from app.infrastructure.irepositories.iaudit_log_repository import IAuditLogRepository
from app.infrastructure.irepositories.icart_repository import ICartRepository
from app.infrastructure.irepositories.iorder_repository import IOrderRepository
from app.infrastructure.irepositories.iproduct_repository import IProductRepository
from app.infrastructure.irepositories.ireview_repository import IReviewRepository
from app.infrastructure.irepositories.iuser_repository import IUserRepository
from app.infrastructure.repositories.audit_log_repository import AuditLogRepository
from app.infrastructure.repositories.cart_repository import CartRepository
from app.infrastructure.repositories.order_repository import OrderRepository
from app.infrastructure.repositories.product_repository import ProductRepository
from app.infrastructure.repositories.review_repository import ReviewRepository
from app.infrastructure.repositories.user_repository import UserRepository


def configure(container: Container, settings: Settings) -> None:
    engine, session_factory = create_engine_and_sessionmaker(settings)
    container.engine = engine
    container.session_factory = session_factory

    container.bind_instance(Settings, settings)

    bus = EventBus()
    register_handlers(bus)
    container.bind_instance(EventBus, bus)

    container.bind(IUserRepository, UserRepository)
    container.bind(IProductRepository, ProductRepository)
    container.bind(ICartRepository, CartRepository)
    container.bind(IOrderRepository, OrderRepository)
    container.bind(IReviewRepository, ReviewRepository)
    container.bind(IAuditLogRepository, AuditLogRepository)

    container.bind(IAuthService, AuthService)
    container.bind(IProductService, ProductService)
    container.bind(ICartService, CartService)
    container.bind(IOrderService, OrderService)
    container.bind(IReviewService, ReviewService)
    container.bind(IAdminService, AdminService)

    container.bind(IAIGateway, AIGateway, singleton=True)

    # Holds no session: it calls the AI service mid-request and opens its own short
    # scopes around database work instead (§8.2).
    container.bind_instance(ScopeFactory, ScopeFactory(container))
    # Not a singleton: it is three attribute assignments to build, and pinning one instance
    # would freeze whichever IAIGateway existed at first resolve — which is exactly what tests
    # rebind, and what a future gateway swap would need to replace.
    container.bind(ICatalogSearchService, CatalogSearchService)
