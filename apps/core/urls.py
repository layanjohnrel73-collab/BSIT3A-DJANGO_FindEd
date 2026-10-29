from django.urls import path
from . import views

urlpatterns = [
    path('', views.login_view, name='login'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('home/', views.home, name='finder'),
    path('ride/', views.ride_view, name='ride'),
    path('street/', views.street_view, name='street'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register_view, name='register'),
]