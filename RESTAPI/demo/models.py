from django.core.files import File
from django.db import models
import os, urllib


# Create your models here.

class BookNum(models.Model):
    isbn_10 = models.CharField(max_length=10, blank=True)
    isbn_13 = models.CharField(max_length=13, blank=True)

    def __str__(self):
        return str(self.isbn_10)


class Book(models.Model):
    numbers = BookNum
    title = models.CharField(max_length=36, unique=True, blank=False)
    description = models.TextField(max_length=256, blank=True)
    Price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    publish_date = models.DateField(null=True, blank=True)
    Is_Famous = models.BooleanField(default=False)
    Covers = models.ImageField(upload_to='covers/', blank=True)
    number = models.OneToOneField(numbers, null=True, blank=True, on_delete=models.CASCADE)

    def __str__(self):
        return self.title


class Character(models.Model):
    name = models.CharField(max_length=30)
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name='characters')
