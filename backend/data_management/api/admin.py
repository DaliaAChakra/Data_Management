from django.contrib import admin

from .models import * 

admin.site.register(FieldSchema)
admin.site.register(TableSchema)