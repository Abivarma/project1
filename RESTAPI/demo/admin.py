from django.contrib import admin
from .models import Book, BookNum, Character


# Register your models here.
@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ['title', 'Price']
    list_filter = ['publish_date']
    search_fields = ['title']


admin.site.register(BookNum)
admin.site.register(Character)

