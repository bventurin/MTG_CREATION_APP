/**
 * Deck Detail Page Functionality
 * Handles AI suggestions loading state, voucher downloads, and QR code interactions
 */

document.addEventListener('DOMContentLoaded', function () {
    // AI Suggestions button loading state
    const aiBtn = document.getElementById('ai-suggestions-btn');
    if (aiBtn) {
        aiBtn.addEventListener('click', function () {
            // Show loading state
            const icon = this.querySelector('i');
            if (icon) {
                icon.className = 'spinner-border spinner-border-sm me-2';
            }
            this.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>Analyzing deck...';
            this.classList.add('disabled');
            this.style.pointerEvents = 'none';
        });
    }

    // Voucher download button
    const downloadBtn = document.getElementById('download-voucher-btn');
    const ticketElement = document.getElementById('voucher-ticket');

    if (downloadBtn && ticketElement) {
        downloadBtn.addEventListener('click', function () {
            // Check if html2canvas is available
            if (typeof window.html2canvas === 'undefined') {
                console.error('html2canvas library is not loaded');
                alert('Unable to generate voucher image. The html2canvas library failed to load. Please check your internet connection and refresh the page.');
                return;
            }

            // Provide feedback while rendering
            const originalText = this.innerHTML;
            this.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>Generating...';
            this.disabled = true;

            // Use window.html2canvas to ensure we're accessing the global
            window.html2canvas(ticketElement, {
                scale: 2,
                backgroundColor: null,
                useCORS: true
            }).then(canvas => {
                // Convert to image and download
                const link = document.createElement('a');
                const voucherCode = ticketElement.dataset.voucherCode || 'promo';
                link.download = `aetherflow_voucher_${voucherCode}.png`;
                link.href = canvas.toDataURL('image/png');
                link.click();

                // Restore button
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