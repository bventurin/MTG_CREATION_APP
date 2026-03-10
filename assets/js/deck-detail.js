/**
 * Deck Detail Page - Client-Side Functionality
 * Handles the loading states for AI suggestions and voucher image downloads
 */

document.addEventListener('DOMContentLoaded', function () {
    // When user clicks "Get AI Suggestions", show a loading spinner while it processes
    const aiBtn = document.getElementById('ai-suggestions-btn');
    if (aiBtn) {
        aiBtn.addEventListener('click', function () {
            // Replace the icon with a spinner
            const icon = this.querySelector('i');
            if (icon) {
                icon.className = 'spinner-border spinner-border-sm me-2';
            }
            this.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>Analyzing deck...';
            this.classList.add('disabled');
            this.style.pointerEvents = 'none';
        });
    }

    // Handle the voucher download functionality
    const downloadBtn = document.getElementById('download-voucher-btn');
    const ticketElement = document.getElementById('voucher-ticket');

    if (downloadBtn && ticketElement) {
        downloadBtn.addEventListener('click', function () {
            // Make sure the html2canvas library actually loaded from the CDN
            if (typeof html2canvas === 'undefined') {
                console.error('html2canvas library is not loaded');
                alert('Unable to generate voucher image. The html2canvas library failed to load. Please check your internet connection and refresh the page.');
                return;
            }

            // Show a loading state while we generate the image
            const originalText = this.innerHTML;
            this.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>Generating...';
            this.disabled = true;

            // Convert the voucher HTML element into a downloadable PNG image
            html2canvas(ticketElement, {
                scale: 2,  // Higher resolution for better quality
                backgroundColor: null,  // Keep transparency
                useCORS: true  // Allow external fonts/images to load
            }).then(canvas => {
                // Create a download link and trigger it automatically
                const link = document.createElement('a');
                const voucherCode = ticketElement.dataset.voucherCode || 'promo';
                link.download = `aetherflow_voucher_${voucherCode}.png`;
                link.href = canvas.toDataURL('image/png');
                link.click();

                // Put the button back to normal
                this.innerHTML = originalText;
                this.disabled = false;
            }).catch(err => {
                console.error('Error generating voucher image:', err);
                alert('Oops! Something went wrong while generating your voucher image. Please try again.');
                this.innerHTML = originalText;
                this.disabled = false;
            });
        });
    }
});