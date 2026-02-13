from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from .services.ai_recommender import get_deck_recommendations


@login_required(login_url='login')
def recommendations(request):
    card_names = []
    if request.method == "POST":
        format_name = request.POST.get("format")
        colors = request.POST.getlist("colors")
        card_names = get_deck_recommendations(format_name, colors)
            
    return render(request, "card_recommender/recommendations.html", {"card_names": card_names})
