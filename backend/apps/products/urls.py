from django.urls import path

from . import views

urlpatterns = [
    # Public endpoints
    path("", views.ProductListView.as_view(), name="product-list"),
    path("featured/", views.featured_products, name="product-featured"),
    path("search/", views.search_products, name="product-search"),
    path("<int:pk>/", views.ProductDetailView.as_view(), name="product-detail"),
    # Listing lifecycle (Phase 13)
    path("<int:pk>/lifecycle/", views.ListingLifecycleView.as_view(), name="listing-lifecycle"),
    path("<int:pk>/similar/", views.similar_listings, name="listing-similar"),
    path(
        "<int:pk>/more-from-seller/",
        views.more_from_seller,
        name="listing-more-from-seller",
    ),
    # Seller endpoints (any signed-in user owns *their* listings — Phase 13)
    path("create/", views.ListingCreateView.as_view(), name="listing-create"),
    path("seller/list/", views.SellerProductListView.as_view(), name="seller-product-list"),
    path("seller/quota/", views.seller_quota, name="seller-quota"),
    path("seller/create/", views.SellerProductCreateView.as_view(), name="seller-product-create"),
    path("seller/<int:pk>/", views.SellerProductDetailView.as_view(), name="seller-product-detail"),
    # Review endpoints
    path(
        "<int:product_id>/reviews/", views.ProductReviewListView.as_view(), name="product-reviews"
    ),
    path("reviews/create/", views.ProductReviewCreateView.as_view(), name="review-create"),
    path("reviews/my-reviews/", views.UserReviewsListView.as_view(), name="user-reviews"),
    path("reviews/<int:pk>/", views.UserReviewDetailView.as_view(), name="review-detail"),
    path("<int:product_id>/check-review/", views.check_user_review, name="check-user-review"),
    # Wishlist endpoints
    path("wishlist/", views.WishlistListView.as_view(), name="wishlist-list"),
    path("wishlist/add/", views.add_to_wishlist, name="wishlist-add"),
    path("wishlist/remove/<int:product_id>/", views.remove_from_wishlist, name="wishlist-remove"),
    path("wishlist/check/<int:product_id>/", views.check_wishlist_status, name="wishlist-check"),
    path("wishlist/clear/", views.clear_wishlist, name="wishlist-clear"),
]
