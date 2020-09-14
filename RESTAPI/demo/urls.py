from django.urls import path, include
from . import views
from rest_framework import routers
from .views import BookViewset

router = routers.DefaultRouter()
router.register('books', BookViewset)

urlpatterns = [
    path('', include(router.urls)),
]
