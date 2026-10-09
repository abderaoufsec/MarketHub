"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { wishlistAPI, cartAPI } from "../../lib/api";
import { useAuth } from "../../context/AuthContext";
import { Heart, ShoppingCart, Trash2, Package } from "lucide-react";
import toast from "react-hot-toast";

export default function WishlistPage() {
  const router = useRouter();
  const { isAuthenticated } = useAuth();
  const [wishlist, setWishlist] = useState([]);
  const [loading, setLoading] = useState(true);
  const [removingIds, setRemovingIds] = useState(new Set());
  const [addingToCartIds, setAddingToCartIds] = useState(new Set());

  useEffect(() => {
    if (!isAuthenticated) {
      router.push("/login");
      return;
    }
    fetchWishlist();
  }, [isAuthenticated]);

  const fetchWishlist = async () => {
    try {
      const response = await wishlistAPI.list();
      // Handle both array response and object with results property
      const wishlistData = Array.isArray(response.data) 
        ? response.data 
        : (response.data?.results || response.data?.items || []);
      setWishlist(wishlistData);
    } catch (error) {
      console.error("Error fetching wishlist:", error);
      toast.error("Failed to load wishlist");
      setWishlist([]); // Set empty array on error
    } finally {
      setLoading(false);
    }
  };

  const handleRemove = async (item) => {
    setRemovingIds(prev => new Set([...prev, item.id]));
    try {
      await wishlistAPI.remove(item.product);
      setWishlist(wishlist.filter((i) => i.id !== item.id));
      toast.success("Removed from wishlist");
    } catch (error) {
      console.error("Error removing from wishlist:", error);
      toast.error("Failed to remove item");
    } finally {
      setRemovingIds(prev => {
        const next = new Set(prev);
        next.delete(item.id);
        return next;
      });
    }
  };

  const handleAddToCart = async (item) => {
    if (!item.product_available) {
      toast.error("This product is currently unavailable");
      return;
    }

    setAddingToCartIds(prev => new Set([...prev, item.id]));
    try {
      await cartAPI.add({
        product_id: item.product,
        quantity: 1,
        selected_attributes: {},
      });
      toast.success("Added to cart!");
    } catch (error) {
      console.error("Error adding to cart:", error);
      const errorMsg = error.response?.data?.error || "Failed to add to cart";
      toast.error(errorMsg);
    } finally {
      setAddingToCartIds(prev => {
        const next = new Set(prev);
        next.delete(item.id);
        return next;
      });
    }
  };

  const handleClearWishlist = async () => {
    if (!window.confirm("Are you sure you want to clear your entire wishlist?")) {
      return;
    }

    try {
      await wishlistAPI.clear();
      setWishlist([]);
      toast.success("Wishlist cleared");
    } catch (error) {
      console.error("Error clearing wishlist:", error);
      toast.error("Failed to clear wishlist");
    }
  };

  if (loading) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="animate-pulse">
          <div className="bg-gray-300 h-8 rounded w-1/4 mb-8"></div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {[...Array(6)].map((_, i) => (
              <div key={i} className="bg-gray-300 h-64 rounded"></div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div className="flex items-center gap-3">
          <Heart className="h-8 w-8 text-primary fill-primary" />
          <div>
            <h1 className="text-3xl font-bold text-gray-900">My Wishlist</h1>
            <p className="text-gray-600">
              {wishlist.length} {wishlist.length === 1 ? "item" : "items"}
            </p>
          </div>
        </div>

        {wishlist.length > 0 && (
          <button
            onClick={handleClearWishlist}
            className="text-sm text-red-600 hover:text-red-700 font-medium"
          >
            Clear Wishlist
          </button>
        )}
      </div>

      {/* Wishlist Content */}
      {wishlist.length === 0 ? (
        <div className="text-center py-16">
          <Heart className="h-16 w-16 text-gray-300 mx-auto mb-4" />
          <h2 className="text-2xl font-bold text-gray-900 mb-2">
            Your wishlist is empty
          </h2>
          <p className="text-gray-600 mb-6">
            Add items you love to your wishlist. Review them anytime and easily move them to your cart.
          </p>
          <button
            onClick={() => router.push("/products")}
            className="btn-primary"
          >
            Start Shopping
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {wishlist.map((item) => (
            <div
              key={item.id}
              className="bg-white rounded-lg shadow-sm overflow-hidden hover:shadow-md transition-shadow"
            >
              {/* Product Image */}
              <div className="relative group">
                <img
                  src={item.product_image || "/placeholder-product.jpg"}
                  alt={item.product_name}
                  className="w-full h-64 object-cover cursor-pointer"
                  onClick={() => router.push(`/products/${item.product}`)}
                />
                {!item.product_available && (
                  <div className="absolute inset-0 bg-black bg-opacity-50 flex items-center justify-center">
                    <span className="bg-red-600 text-white px-4 py-2 rounded-full text-sm font-semibold">
                      Out of Stock
                    </span>
                  </div>
                )}
                <button
                  onClick={() => handleRemove(item)}
                  disabled={removingIds.has(item.id)}
                  className="absolute top-3 right-3 p-2 bg-white rounded-full shadow-md hover:bg-red-50 transition-colors disabled:opacity-50"
                >
                  {removingIds.has(item.id) ? (
                    <div className="animate-spin h-5 w-5 border-2 border-red-600 border-t-transparent rounded-full"></div>
                  ) : (
                    <Trash2 className="h-5 w-5 text-red-600" />
                  )}
                </button>
              </div>

              {/* Product Info */}
              <div className="p-4">
                <h3
                  className="font-semibold text-gray-900 mb-2 cursor-pointer hover:text-primary line-clamp-2"
                  onClick={() => router.push(`/products/${item.product}`)}
                >
                  {item.product_name}
                </h3>
                <p className="text-2xl font-bold text-primary mb-4">
                  ${parseFloat(item.product_price).toFixed(2)}
                </p>

                <div className="flex gap-2">
                  <button
                    onClick={() => handleAddToCart(item)}
                    disabled={
                      !item.product_available || addingToCartIds.has(item.id)
                    }
                    className="flex-1 btn-primary disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                  >
                    {addingToCartIds.has(item.id) ? (
                      <>
                        <div className="animate-spin h-4 w-4 border-2 border-white border-t-transparent rounded-full"></div>
                        Adding...
                      </>
                    ) : (
                      <>
                        <ShoppingCart className="h-4 w-4" />
                        Add to Cart
                      </>
                    )}
                  </button>
                  <button
                    onClick={() => router.push(`/products/${item.product}`)}
                    className="p-2 border border-gray-300 rounded-lg hover:bg-gray-50"
                    title="View product"
                  >
                    <Package className="h-5 w-5 text-gray-600" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
