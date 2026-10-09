"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { cartAPI, ordersAPI, addressesAPI, paymentsAPI } from "../../lib/api";
import { useAuth } from "../../context/AuthContext";
import { CreditCard, MapPin, Package, AlertCircle, CheckCircle, Plus, Loader2 } from "lucide-react";
import toast from "react-hot-toast";

export default function CheckoutPage() {
  const router = useRouter();
  const { isAuthenticated } = useAuth();
  const [cart, setCart] = useState(null);
  const [addresses, setAddresses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState(false);
  const [processingPayment, setProcessingPayment] = useState(false);
  const [error, setError] = useState("");
  const [selectedAddressId, setSelectedAddressId] = useState(null);
  const [showNewAddressForm, setShowNewAddressForm] = useState(false);
  const [paymentMethod, setPaymentMethod] = useState("credit_card");
  const [shippingInfo, setShippingInfo] = useState({
    address_line1: "",
    address_line2: "",
    city: "",
    state_province: "",
    postal_code: "",
    country: "",
    is_default: false,
  });

  useEffect(() => {
    if (!isAuthenticated) {
      router.push("/login");
      return;
    }
    fetchCart();
    fetchAddresses();
  }, [isAuthenticated]);

  const fetchCart = async () => {
    try {
      const response = await cartAPI.get();
      setCart(response.data);
      if (!response.data?.items || response.data.items.length === 0) {
        router.push("/cart");
      }
    } catch (error) {
      console.error("Error fetching cart:", error);
      setError("Failed to load cart");
    } finally {
      setLoading(false);
    }
  };

  const fetchAddresses = async () => {
    try {
      const response = await addressesAPI.list();
      const addressesData = response.data.results || response.data || [];
      setAddresses(addressesData);
      // Select default address if available
      const defaultAddress = addressesData.find((addr) => addr.is_default);
      if (defaultAddress) {
        setSelectedAddressId(defaultAddress.id);
      } else if (addressesData.length > 0) {
        setSelectedAddressId(addressesData[0].id);
      }
    } catch (error) {
      console.error("Error fetching addresses:", error);
    }
  };

  const handleCreateAddress = async (e) => {
    e.preventDefault();
    setError("");

    try {
      const response = await addressesAPI.create(shippingInfo);
      toast.success("Address saved successfully");
      await fetchAddresses();
      setSelectedAddressId(response.data.id);
      setShowNewAddressForm(false);
      setShippingInfo({
        address_line1: "",
        address_line2: "",
        city: "",
        state_province: "",
        postal_code: "",
        country: "",
        is_default: false,
      });
    } catch (error) {
      console.error("Error creating address:", error);
      const errorMsg =
        error.response?.data?.detail ||
        Object.values(error.response?.data || {})[0]?.[0] ||
        "Failed to save address";
      setError(errorMsg);
      toast.error(errorMsg);
    }
  };

  const handleCheckout = async (e) => {
    e.preventDefault();
    setError("");
    setProcessing(true);

    try {
      // Validate cart has items
      if (!cart?.items || cart.items.length === 0) {
        setError("Your cart is empty");
        setProcessing(false);
        return;
      }

      // If using new address form, create address first
      let addressId = selectedAddressId;
      
      if (showNewAddressForm && !addressId) {
        // Validate required fields
        if (!shippingInfo.address_line1 || !shippingInfo.city || 
            !shippingInfo.state_province || !shippingInfo.postal_code || 
            !shippingInfo.country) {
          setError("Please fill in all required address fields");
          setProcessing(false);
          return;
        }
        
        const addressResponse = await addressesAPI.create(shippingInfo);
        addressId = addressResponse.data.id;
      }

      if (!addressId) {
        setError("Please select or create a shipping address");
        setProcessing(false);
        return;
      }

      // Create order using address ID
      const checkoutData = {
        shipping_address_id: addressId,
        shipping_method: "standard",
      };

      const response = await ordersAPI.checkout(checkoutData);
      
      toast.success("Order created successfully!");
      
      // Get order ID
      const orderId = response.data.orders?.[0]?.id || response.data.id;
      
      // Process payment simulation
      setProcessingPayment(true);
      
      try {
        const paymentResponse = await paymentsAPI.simulatePayment({
          order_id: orderId,
          payment_method: paymentMethod
        });
        
        toast.success("Payment processed successfully!");
        
        // Redirect to order details
        router.push(`/orders/${orderId}?success=true`);
      } catch (paymentError) {
        console.error("Payment error:", paymentError);
        // Order created but payment failed
        toast.error("Payment failed. Order created but not paid.");
        router.push(`/orders/${orderId}?payment_failed=true`);
      }
    } catch (error) {
      console.error("Checkout error:", error);
      const errorMsg =
        error.response?.data?.error ||
        error.response?.data?.detail ||
        Object.values(error.response?.data || {})[0]?.[0] ||
        "Failed to process order. Please try again.";
      setError(errorMsg);
      toast.error(errorMsg);
    } finally {
      setProcessing(false);
      setProcessingPayment(false);
    }
  };

  const handleInputChange = (e) => {
    const { name, value, type, checked } = e.target;
    setShippingInfo({
      ...shippingInfo,
      [name]: type === "checkbox" ? checked : value,
    });
  };

  const getTotal = () => {
    if (!cart?.items) return 0;
    return cart.items.reduce((sum, item) => {
      return sum + parseFloat(item.price_at_time_of_addition) * item.quantity;
    }, 0);
  };

  if (loading) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-8">
        <div className="animate-pulse">
          <div className="bg-gray-300 h-8 rounded w-1/4 mb-8"></div>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
            <div className="lg:col-span-2 bg-gray-300 h-96 rounded"></div>
            <div className="bg-gray-300 h-64 rounded"></div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <h1 className="text-3xl font-bold text-gray-900 mb-8">Checkout</h1>

      {error && (
        <div className="mb-6 bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg flex items-center">
          <AlertCircle className="h-5 w-5 mr-2" />
          <span>{error}</span>
        </div>
      )}

      <form onSubmit={showNewAddressForm ? handleCreateAddress : handleCheckout}>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Checkout Form */}
          <div className="lg:col-span-2 space-y-6">
            {/* Shipping Information */}
            <div className="bg-white rounded-lg shadow-sm p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xl font-bold text-gray-900 flex items-center">
                  <MapPin className="h-5 w-5 mr-2" />
                  Shipping Address
                </h2>
                {!showNewAddressForm && (
                  <button
                    type="button"
                    onClick={() => setShowNewAddressForm(true)}
                    className="flex items-center gap-2 text-sm text-primary hover:text-secondary"
                  >
                    <Plus className="h-4 w-4" />
                    Add New Address
                  </button>
                )}
              </div>

              {!showNewAddressForm ? (
                // Address Selection
                <div className="space-y-3">
                  {addresses.length > 0 ? (
                    addresses.map((address) => (
                      <label
                        key={address.id}
                        className={`block p-4 border-2 rounded-lg cursor-pointer transition-all ${
                          selectedAddressId === address.id
                            ? "border-primary bg-primary/5"
                            : "border-gray-200 hover:border-gray-300"
                        }`}
                      >
                        <input
                          type="radio"
                          name="address"
                          value={address.id}
                          checked={selectedAddressId === address.id}
                          onChange={(e) => setSelectedAddressId(parseInt(e.target.value))}
                          className="sr-only"
                        />
                        <div className="flex items-start justify-between">
                          <div className="flex-1">
                            <div className="flex items-center gap-2 mb-2">
                              <span className="font-semibold text-gray-900">
                                {address.address_line1}
                              </span>
                              {address.is_default && (
                                <span className="px-2 py-0.5 text-xs bg-primary text-white rounded">
                                  Default
                                </span>
                              )}
                            </div>
                            {address.address_line2 && (
                              <p className="text-sm text-gray-600">{address.address_line2}</p>
                            )}
                            <p className="text-sm text-gray-600">
                              {address.city}, {address.state_province} {address.postal_code}
                            </p>
                            <p className="text-sm text-gray-600">{address.country}</p>
                          </div>
                          {selectedAddressId === address.id && (
                            <CheckCircle className="h-5 w-5 text-primary flex-shrink-0" />
                          )}
                        </div>
                      </label>
                    ))
                  ) : (
                    <div className="text-center py-8 text-gray-500">
                      <p>No saved addresses. Please add a shipping address.</p>
                    </div>
                  )}
                </div>
              ) : (
                // New Address Form
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Address Line 1 *
                    </label>
                    <input
                      type="text"
                      name="address_line1"
                      required
                      value={shippingInfo.address_line1}
                      onChange={handleInputChange}
                      className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-primary focus:border-primary"
                      placeholder="Street address"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Address Line 2
                    </label>
                    <input
                      type="text"
                      name="address_line2"
                      value={shippingInfo.address_line2}
                      onChange={handleInputChange}
                      className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-primary focus:border-primary"
                      placeholder="Apartment, suite, etc. (optional)"
                    />
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        City *
                      </label>
                      <input
                        type="text"
                        name="city"
                        required
                        value={shippingInfo.city}
                        onChange={handleInputChange}
                        className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-primary focus:border-primary"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        State/Province *
                      </label>
                      <input
                        type="text"
                        name="state_province"
                        required
                        value={shippingInfo.state_province}
                        onChange={handleInputChange}
                        className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-primary focus:border-primary"
                      />
                    </div>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        Postal Code *
                      </label>
                      <input
                        type="text"
                        name="postal_code"
                        required
                        value={shippingInfo.postal_code}
                        onChange={handleInputChange}
                        className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-primary focus:border-primary"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        Country *
                      </label>
                      <input
                        type="text"
                        name="country"
                        required
                        value={shippingInfo.country}
                        onChange={handleInputChange}
                        className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-primary focus:border-primary"
                      />
                    </div>
                  </div>
                  <div className="flex items-center">
                    <input
                      type="checkbox"
                      name="is_default"
                      id="is_default"
                      checked={shippingInfo.is_default}
                      onChange={handleInputChange}
                      className="h-4 w-4 text-primary focus:ring-primary border-gray-300 rounded"
                    />
                    <label htmlFor="is_default" className="ml-2 text-sm text-gray-700">
                      Set as default address
                    </label>
                  </div>
                  <div className="flex gap-3">
                    <button
                      type="submit"
                      className="btn-primary flex-1"
                    >
                      Save Address
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setShowNewAddressForm(false);
                        setShippingInfo({
                          address_line1: "",
                          address_line2: "",
                          city: "",
                          state_province: "",
                          postal_code: "",
                          country: "",
                          is_default: false,
                        });
                      }}
                      className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* Payment Information */}
            {!showNewAddressForm && (
              <div className="bg-white rounded-lg shadow-sm p-6">
                <h2 className="text-xl font-bold text-gray-900 mb-4 flex items-center">
                  <CreditCard className="h-5 w-5 mr-2" />
                  Payment Method
                </h2>
                
                <div className="space-y-3 mb-4">
                  <label className="flex items-center p-4 border-2 rounded-lg cursor-pointer border-primary bg-primary/5">
                    <input
                      type="radio"
                      name="payment_method"
                      value="credit_card"
                      checked={paymentMethod === "credit_card"}
                      onChange={(e) => setPaymentMethod(e.target.value)}
                      className="h-4 w-4 text-primary"
                    />
                    <CreditCard className="h-5 w-5 mx-3 text-primary" />
                    <span className="font-medium">Credit/Debit Card</span>
                  </label>
                </div>
                
                <div className="bg-blue-50 border border-blue-200 text-blue-700 px-4 py-3 rounded-lg">
                  <p className="text-sm">
                    <strong>🔒 Simulated Payment:</strong> This is a demo payment system. 
                    No real payment will be processed. Your order will be automatically approved.
                  </p>
                </div>
              </div>
            )}
          </div>

          {/* Order Summary */}
          {!showNewAddressForm && (
            <div className="lg:col-span-1">
              <div className="bg-white rounded-lg shadow-sm p-6 sticky top-4">
                <h2 className="text-xl font-bold text-gray-900 mb-4 flex items-center">
                  <Package className="h-5 w-5 mr-2" />
                  Order Summary
                </h2>

                <div className="space-y-3 mb-4 max-h-64 overflow-y-auto">
                  {cart?.items?.map((item) => (
                    <div key={item.id} className="flex items-center gap-3">
                      <img
                        src={
                          item.product?.images?.[0]?.image_url ||
                          "/placeholder-product.jpg"
                        }
                        alt={item.product?.name}
                        className="w-16 h-16 object-cover rounded"
                      />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-semibold text-gray-900 truncate">
                          {item.product?.name}
                        </p>
                        <p className="text-sm text-gray-600">
                          Qty: {item.quantity} × $
                          {parseFloat(item.price_at_time_of_addition).toFixed(2)}
                        </p>
                      </div>
                      <p className="text-sm font-semibold">
                        $
                        {(
                          parseFloat(item.price_at_time_of_addition) *
                          item.quantity
                        ).toFixed(2)}
                      </p>
                    </div>
                  ))}
                </div>

                <div className="border-t pt-4 space-y-2 mb-4">
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-600">Subtotal</span>
                    <span className="font-semibold">
                      ${getTotal().toFixed(2)}
                    </span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-600">Shipping</span>
                    <span className="font-semibold">Free</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-600">Tax</span>
                    <span className="font-semibold">$0.00</span>
                  </div>
                </div>

                <div className="border-t pt-4 mb-6">
                  <div className="flex justify-between text-lg font-bold">
                    <span>Total</span>
                    <span className="text-primary">${getTotal().toFixed(2)}</span>
                  </div>
                </div>

                <button
                  type="submit"
                  disabled={processing || processingPayment || !selectedAddressId}
                  className="w-full btn-primary disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                >
                  {processing || processingPayment ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      {processingPayment ? "Processing Payment..." : "Creating Order..."}
                    </>
                  ) : (
                    "Place Order & Pay"
                  )}
                </button>

                <p className="text-xs text-gray-500 text-center mt-4">
                  By placing your order, you agree to our Terms of Service and
                  Privacy Policy.
                </p>
              </div>
            </div>
          )}
        </div>
      </form>
    </div>
  );
}
