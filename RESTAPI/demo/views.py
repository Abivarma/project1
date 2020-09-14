from .models import Book
from rest_framework import viewsets
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from .serial import BookSerial

# Create your views here.

class BookViewset(viewsets.ModelViewSet):
    serializer_class = BookSerial
    queryset = Book.objects.all()
    authentication_classes = (TokenAuthentication,)
    permission_classes = (IsAuthenticated,)

