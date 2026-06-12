from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.core.paginator import Paginator
from .models import Service, Category
from .forms import ServiceForm

def home(request):
    cats = Category.objects.filter(is_active=True)[:10]
    featured = Service.objects.filter(is_active=True).select_related('provider','provider__provider_profile','category')[:8]
    from accounts.models import ProviderProfile
    top = ProviderProfile.objects.filter(is_active=True).order_by('-rating')[:6]
    return render(request, 'home.html', {'cats':cats,'featured':featured,'top':top})

def service_list(request):
    qs = Service.objects.filter(is_active=True).select_related('provider','provider__provider_profile','category')
    cats = Category.objects.filter(is_active=True)
    q = request.GET.get('q',''); cat = request.GET.get('cat',''); sort = request.GET.get('sort','-created_at')
    if q: qs = qs.filter(Q(title__icontains=q)|Q(description__icontains=q)|Q(tags__icontains=q)|Q(provider__provider_profile__business_name__icontains=q))
    if cat: qs = qs.filter(category__slug=cat)
    if sort in ['-created_at','price','-price']: qs = qs.order_by(sort)
    paged = Paginator(qs,12).get_page(request.GET.get('page'))
    return render(request,'services/list.html',{'services':paged,'cats':cats,'q':q,'cat':cat,'sort':sort})

def service_detail(request, pk):
    svc = get_object_or_404(Service, pk=pk, is_active=True)
    from bookings.models import Review
    reviews = Review.objects.filter(service=svc).select_related('customer').order_by('-created_at')[:10]
    others = Service.objects.filter(provider=svc.provider, is_active=True).exclude(pk=pk)[:4]
    is_saved = False
    if request.user.is_authenticated:
        from accounts.models import SavedProvider
        is_saved = SavedProvider.objects.filter(customer=request.user, provider=svc.provider).exists()
    return render(request,'services/detail.html',{'svc':svc,'reviews':reviews,'others':others,'is_saved':is_saved})

@login_required
def my_services(request):
    if not request.user.is_provider: return redirect('dashboard')
    svcs = Service.objects.filter(provider=request.user)
    return render(request,'services/my_services.html',{'svcs':svcs})

@login_required
def service_create(request):
    if not request.user.is_provider: return redirect('dashboard')
    form = ServiceForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        svc = form.save(commit=False); svc.provider = request.user; svc.save()
        messages.success(request, f'"{svc.title}" created!'); return redirect('my_services')
    return render(request,'services/form.html',{'form':form,'action':'New Service'})

@login_required
def service_edit(request, pk):
    svc = get_object_or_404(Service, pk=pk, provider=request.user)
    form = ServiceForm(request.POST or None, request.FILES or None, instance=svc)
    if request.method == 'POST' and form.is_valid():
        form.save(); messages.success(request,'Service updated!'); return redirect('my_services')
    return render(request,'services/form.html',{'form':form,'action':'Edit Service','svc':svc})

@login_required
def service_delete(request, pk):
    svc = get_object_or_404(Service, pk=pk, provider=request.user)
    if request.method == 'POST':
        svc.is_active=False; svc.save(); messages.success(request,'Service removed.'); return redirect('my_services')
    return render(request,'services/delete.html',{'svc':svc})
