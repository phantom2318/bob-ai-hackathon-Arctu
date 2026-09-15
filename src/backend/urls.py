from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect

# Redirect the home page to your predictions API
def redirect_to_api(request):
    return redirect('/api/predictions/')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', redirect_to_api, name='home'),
    
    # This restores your app routes so /api/predictions/ works again!
    path('api/', include('api.urls')), 
]
