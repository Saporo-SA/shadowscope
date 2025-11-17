/**
 * Azure Resources JavaScript
 * Handles pagination and dynamic loading for Azure resource pages
 */

// Global variables for pagination
let currentPage = 1;
let isLoading = false;

// Function to fetch subscriptions with pagination
async function fetchSubscriptions(limit = 15, offset = 0) {
    if (isLoading) return;
    
    isLoading = true;
    const loadingIndicator = document.getElementById('loadingIndicator');
    if (loadingIndicator) {
        loadingIndicator.style.display = 'block';
    }

    try {
        const response = await fetch(`/subscriptions?limit=${limit}&offset=${offset}`, {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
            }
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        displaySubscriptions(data);
    } catch (error) {
        console.error('Error fetching subscriptions:', error);
        if (window.ShadowScopeNotifications) {
            window.ShadowScopeNotifications.error('Failed to load subscriptions');
        }
    } finally {
        isLoading = false;
        if (loadingIndicator) {
            loadingIndicator.style.display = 'none';
        }
    }
}

// Function to display subscriptions
function displaySubscriptions(data) {
    const tbody = document.getElementById('subscriptionsTableBody');
    if (!tbody) return;

    // Clear existing content
    tbody.innerHTML = '';

    if (data.subscriptions && data.subscriptions.length > 0) {
        data.subscriptions.forEach(subscription => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>
                    <div class="d-flex align-items-center">
                        <i class="bi bi-collection me-2 text-primary"></i>
                        <div>
                            <div class="fw-bold">${subscription.displayName || subscription.name || 'N/A'}</div>
                            <small class="text-muted">${subscription.subscriptionId}</small>
                        </div>
                    </div>
                </td>
                <td>
                    <span class="badge bg-${subscription.state === 'Enabled' ? 'success' : 'secondary'}">
                        ${subscription.state || 'Unknown'}
                    </span>
                </td>
                <td>
                    <div class="d-flex align-items-center">
                        <i class="bi bi-building me-2"></i>
                        <span>${subscription.tenantId || 'N/A'}</span>
                    </div>
                </td>
                <td>
                    <a href="/subscriptions/${subscription.subscriptionId}" class="btn btn-sm btn-outline-primary">
                        <i class="bi bi-eye"></i> View Details
                    </a>
                </td>
            `;
            tbody.appendChild(row);
        });

        // Update pagination info
        updatePaginationInfo(data);
    } else {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td colspan="4" class="text-center text-muted py-4">
                <i class="bi bi-inbox fs-1 d-block mb-2"></i>
                No subscriptions found
            </td>
        `;
        tbody.appendChild(row);
    }
}

// Function to update pagination info
function updatePaginationInfo(data) {
    const paginationInfo = document.getElementById('paginationInfo');
    if (paginationInfo) {
        const start = data.offset + 1;
        const end = Math.min(data.offset + data.limit, data.total_count);
        paginationInfo.textContent = `Showing ${start}-${end} of ${data.total_count} subscriptions`;
    }

    const loadMoreBtn = document.getElementById('loadMoreBtn');
    if (loadMoreBtn) {
        loadMoreBtn.style.display = data.has_more ? 'block' : 'none';
    }
}

// Load more function
function loadMore() {
    if (isLoading) return;
    
    currentPage++;
    const limit = 15;
    const offset = (currentPage - 1) * limit;
    
    fetchSubscriptions(limit, offset);
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    // Load initial data
    fetchSubscriptions();
    
    // Add event listener for load more button
    const loadMoreBtn = document.getElementById('loadMoreBtn');
    if (loadMoreBtn) {
        loadMoreBtn.addEventListener('click', loadMore);
    }
});
