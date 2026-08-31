from django.urls import path

from storefront import views

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
    path("reports/orders.<str:fmt>", views.export_orders, name="export_orders"),
    path("reports/sales.<str:fmt>", views.export_sales, name="export_sales"),
    path("reports/users.<str:fmt>", views.export_users, name="export_users"),
]
