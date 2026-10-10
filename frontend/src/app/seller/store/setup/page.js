'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '../../../../context/AuthContext'
import { storesAPI } from '../../../../lib/api'
import { Store, Save, AlertCircle, CheckCircle, ArrowRight } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import toast from 'react-hot-toast'
import LoadingSpinner from '../../../../components/common/LoadingSpinner'

export default function StoreSetupPage() {
  const router = useRouter()
  const { isAuthenticated, isSeller, loading: authLoading } = useAuth()
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState(null)
  const [formData, setFormData] = useState({
    store_name: '',
    description: '',
    category: '',
  })

  useEffect(() => {
    if (!authLoading && (!isAuthenticated || !isSeller)) {
      router.push('/login')
    }
  }, [authLoading, isAuthenticated, isSeller, router])

  const handleChange = (e) => {
    const { name, value } = e.target
    setFormData((prev) => ({ ...prev, [name]: value }))
  }

  const handleSubmit = async (e) => {
    e.preventDefault()

    if (!formData.store_name || !formData.description || !formData.category) {
      const errorMsg = 'Please fill in all required fields'
      setMessage({ type: 'error', text: errorMsg })
      toast.error(errorMsg)
      return
    }

    // Validate store name length
    if (formData.store_name.length < 3) {
      const errorMsg = 'Store name must be at least 3 characters long'
      setMessage({ type: 'error', text: errorMsg })
      toast.error(errorMsg)
      return
    }

    // Validate description length
    if (formData.description.length < 20) {
      const errorMsg = 'Store description must be at least 20 characters long'
      setMessage({ type: 'error', text: errorMsg })
      toast.error(errorMsg)
      return
    }

    try {
      setLoading(true)
      setMessage(null)
      console.log('Submitting store data:', formData) // Debug log
      const response = await storesAPI.create(formData)
      const successMsg = 'Store created successfully!'
      setMessage({ type: 'success', text: successMsg })
      toast.success(successMsg)
      setTimeout(() => {
        router.push('/seller/dashboard')
      }, 2000)
    } catch (error) {
      console.error('Error creating store:', error)
      console.error('Error response:', error.response) // Debug log

      let errorMsg = 'Failed to create store'

      if (error.response?.data) {
        if (error.response.data.detail) {
          errorMsg = error.response.data.detail
        } else if (error.response.data.store_name) {
          errorMsg = Array.isArray(error.response.data.store_name)
            ? error.response.data.store_name[0]
            : error.response.data.store_name
        } else if (error.response.data.category) {
          errorMsg = Array.isArray(error.response.data.category)
            ? error.response.data.category[0]
            : error.response.data.category
        } else if (error.response.data.error) {
          errorMsg = error.response.data.error
        } else if (typeof error.response.data === 'string') {
          errorMsg = error.response.data
        } else if (error.response.data.non_field_errors) {
          errorMsg = Array.isArray(error.response.data.non_field_errors)
            ? error.response.data.non_field_errors[0]
            : error.response.data.non_field_errors
        }
      }

      setMessage({ type: 'error', text: errorMsg })
      toast.error(errorMsg)
    } finally {
      setLoading(false)
    }
  }

  if (authLoading || !isAuthenticated || !isSeller) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-gray-50 to-gray-100">
        <LoadingSpinner size="xl" />
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 py-12 px-4 sm:px-6 lg:px-8">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="max-w-2xl mx-auto"
      >
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="text-center mb-8"
        >
          <motion.div
            whileHover={{ scale: 1.1, rotate: [0, -5, 5, -5, 0] }}
            transition={{ duration: 0.5 }}
            className="bg-gradient-to-br from-primary/20 to-secondary/20 rounded-full p-4 w-20 h-20 mx-auto mb-4 flex items-center justify-center shadow-lg"
          >
            <Store className="h-10 w-10 text-primary" />
          </motion.div>
          <h1 className="text-4xl font-bold gradient-text mb-2">
            Create Your Store
          </h1>
          <p className="text-gray-600 text-lg">
            Set up your storefront to start selling on MarketHub
          </p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.2 }}
          className="bg-white rounded-xl shadow-lg border border-gray-200 p-8"
        >
          <AnimatePresence>
            {message && (
              <motion.div
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 20 }}
                className={`mb-6 p-4 rounded-lg flex items-center shadow-sm ${
                  message.type === 'success'
                    ? 'bg-green-50 border border-green-200 text-green-700'
                    : 'bg-red-50 border border-red-200 text-red-700'
                }`}
              >
                {message.type === 'success' ? (
                  <CheckCircle className="h-5 w-5 mr-2 flex-shrink-0" />
                ) : (
                  <AlertCircle className="h-5 w-5 mr-2 flex-shrink-0" />
                )}
                <span>{message.text}</span>
              </motion.div>
            )}
          </AnimatePresence>

          <motion.form
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
            onSubmit={handleSubmit}
            className="space-y-6"
          >
            <motion.div
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.4 }}
            >
              <label
                htmlFor="store_name"
                className="block text-sm font-medium text-gray-700 mb-2"
              >
                Store Name <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                id="store_name"
                name="store_name"
                value={formData.store_name}
                onChange={handleChange}
                required
                minLength={3}
                className="input-field"
                placeholder="Enter your store name (min. 3 characters)"
              />
              <p className="text-sm text-gray-500 mt-1">
                This will be your store's public name
              </p>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.5 }}
            >
              <label
                htmlFor="description"
                className="block text-sm font-medium text-gray-700 mb-2"
              >
                Store Description <span className="text-red-500">*</span>
              </label>
              <textarea
                id="description"
                name="description"
                value={formData.description}
                onChange={handleChange}
                required
                minLength={20}
                rows={4}
                className="input-field resize-none"
                placeholder="Tell customers about your store and what you sell (min. 20 characters)"
              />
              <p className="text-sm text-gray-500 mt-1">
                {formData.description.length}/20 characters minimum
              </p>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.6 }}
            >
              <label
                htmlFor="category"
                className="block text-sm font-medium text-gray-700 mb-2"
              >
                Store Category <span className="text-red-500">*</span>
              </label>
              <select
                id="category"
                name="category"
                value={formData.category}
                onChange={handleChange}
                required
                className="input-field"
              >
                <option value="">Select a category</option>
                <option value="electronics">Electronics</option>
                <option value="fashion">Clothing & Fashion</option>
                <option value="home">Home & Garden</option>
                <option value="books">Books & Media</option>
                <option value="sports">Sports & Outdoors</option>
                <option value="toys">Toys & Games</option>
                <option value="beauty">Beauty & Health</option>
                <option value="food">Food & Beverages</option>
                <option value="other">Other</option>
              </select>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.7 }}
              className="bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-200 rounded-lg p-4 shadow-sm"
            >
              <h3 className="text-sm font-semibold text-blue-900 mb-2 flex items-center gap-2">
                <ArrowRight className="h-4 w-4" />
                What's Next?
              </h3>
              <ul className="text-sm text-blue-800 space-y-1 ml-6">
                <li>• Add products to your store</li>
                <li>• Set up inventory tracking</li>
                <li>• Start receiving orders</li>
              </ul>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.8 }}
              className="flex gap-4 pt-6 border-t"
            >
              <motion.button
                type="submit"
                disabled={loading}
                whileHover={{ scale: loading ? 1 : 1.02 }}
                whileTap={{ scale: loading ? 1 : 0.98 }}
                className="flex-1 btn-primary flex items-center justify-center gap-2 disabled:opacity-50 shadow-lg hover:shadow-xl"
              >
                {loading ? (
                  <>
                    <LoadingSpinner size="sm" />
                    Creating Store...
                  </>
                ) : (
                  <>
                    <Save className="h-5 w-5" />
                    Create Store
                  </>
                )}
              </motion.button>
            </motion.div>
          </motion.form>
        </motion.div>
      </motion.div>
    </div>
  )
}
