from django.urls import path
from MTG_CREATION_APP import views

urlpatterns = [
    path('', views.home, name='home'),
]