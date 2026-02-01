from django.shortcuts import render
from .services.ai_recommender import CardRecommender

def recommendations(request):
    recs = []
    if request.method == 'POST':
        format_name = request.POST.get('format')
        colors = request.POST.getlist('colors')
        recs = CardRecommender.get_recommendations(format_name, colors)
        
    return render(request, 'card_recommender/index.html', {'recommendations': recs})
