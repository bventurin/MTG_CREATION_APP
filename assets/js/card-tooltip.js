// Card image hover tooltip
// Shows card image preview when hovering over card names in deck tables
document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.card-name-hover').forEach(function (cardName) {
        cardName.addEventListener('mouseenter', function (e) {
            var row = cardName.closest('.card-row');
            var imageUrl = row.dataset.image;
            if (!imageUrl) return;
            var tooltip = document.getElementById('card-image-tooltip');
            var img = document.getElementById('tooltip-image');
            img.src = imageUrl;
            tooltip.style.display = 'block';
            function updatePosition(e) {
                var tooltipHeight = tooltip.offsetHeight || 300;
                var spaceBelow = window.innerHeight - e.clientY;
                if (spaceBelow < tooltipHeight + 30) {
                    tooltip.style.top = (e.clientY - tooltipHeight - 15) + 'px';
                } else {
                    tooltip.style.top = (e.clientY + 15) + 'px';
                }
                tooltip.style.left = (e.clientX + 15) + 'px';
            }
            updatePosition(e);
            cardName.addEventListener('mousemove', updatePosition);
            cardName.addEventListener('mouseleave', function () {
                tooltip.style.display = 'none';
                cardName.removeEventListener('mousemove', updatePosition);
            }, { once: true });
        });
    });
});
