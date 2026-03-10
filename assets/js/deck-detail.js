/**
 * Deck Detail Page - Client-Side Functionality
 * Handles the loading states for AI suggestions and voucher image downloads
 * Also handles auto-refresh for async-generated mana curve plots
 */

document.addEventListener('DOMContentLoaded', function () {
    // Auto-refresh mana curve plot if it's generating in the background
    const manaCurvePlaceholder = document.getElementById('mana-curve-placeholder');

    if (manaCurvePlaceholder) {
        console.log('Mana curve placeholder detected - starting polling');

        // Extract deck ID from URL (e.g., /decks/abc-123-def/)
        const deckId = window.location.pathname.split('/')[2];
        const checkUrl = `/decks/${deckId}/plot-status/`;

        // Poll for it every 3 seconds for up to 30 seconds
        let pollCount = 0;
        const maxPolls = 10;  // 10 polls × 3 seconds = 30 seconds max

        const pollInterval = setInterval(function() {
            pollCount++;
            console.log(`Polling for mana curve (attempt ${pollCount}/${maxPolls})...`);

            // Check if plot is ready via lightweight JSON endpoint
            fetch(checkUrl)
            .then(response => response.json())
            .then(data => {
                if (data.ready && data.url) {
                    // Plot is ready! Reload the page to show it
                    console.log('Mana curve plot is ready, reloading page...');
                    clearInterval(pollInterval);
                    window.location.reload();
                } else if (pollCount >= maxPolls) {
                    // Timeout - stop polling and show message
                    clearInterval(pollInterval);
                    console.log('Mana curve plot generation timed out');

                    // Update placeholder to show timeout message
                    const cardBody = manaCurvePlaceholder.querySelector('.card-body');
                    if (cardBody) {
                        cardBody.innerHTML = `
                            <div class="d-flex flex-column align-items-center justify-content-center" style="min-height: 200px;">
                                <i class="bi bi-exclamation-triangle text-warning mb-3" style="font-size: 2rem;"></i>
                                <p class="text-muted mb-2">Plot generation is taking longer than expected</p>
                                <button class="btn btn-sm btn-primary" onclick="window.location.reload()">
                                    <i class="bi bi-arrow-clockwise me-1"></i>Refresh Page
                                </button>
                            </div>
                        `;
                    }
                } else {
                    console.log('Plot not ready yet, will retry...');
                }
            })
            .catch(err => {
                console.error('Error polling for mana curve:', err);
                if (pollCount >= maxPolls) {
                    clearInterval(pollInterval);
                }
            });
        }, 3000);
    }

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