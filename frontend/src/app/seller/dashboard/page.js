'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '../../../context/AuthContext'
import { storesAPI, productsAPI, ordersAPI } from '../../../lib/api'
import { parseApiError } from '../../../lib/errors'
import { usePrice } from '../../../lib/currency'
import { useTranslations } from 'next-intl'
import Link from 'next/link'
import {
  Package,
  ShoppingBag,
  DollarSign,
  TrendingUp,
  Store,
  Plus,
  AlertCircle,
  Eye,
  Edit,
  Users,
  Calendar,
  ArrowUpRight,
  ArrowDownRight,
  Bell,
  Settings,
  CheckCircle,
  Clock,
  XCircle,
  Search,
  Filter,
  BarChart3,
} from 'lucide-react'

export default function SellerDashboard() {
  const router = useRouter()
  const t = useTranslations('seller')
  const price = usePrice()
  const { isAuthenticated, user, isSeller, loading: authLoading } = useAuth()
  const [store, setStore] = useState(null)
  const [stats, setStats] = useState(null)
  const [products, setProducts] = useState([])
  const [recentOrders, setRecentOrders] = useState([])
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState('overview')
  const [dateRange, setDateRange] = useState('7d')

  useEffect(() => {
    if (!authLoading) {
      if (!isAuthenticated) {
        router.push('/login')
      } else if (!isSeller) {
        router.push('/')
      }
    }
  }, [authLoading, isAuthenticated, isSeller, router])

  useEffect(() => {
    if (isAuthenticated && isSeller) {
      fetchDashboardData()
    }
  }, [isAuthenticated, isSeller])

  const fetchDashboardData = async () => {
    try {
      setLoading(true)

      // Fetch store info
      try {
        const storeResponse = await storesAPI.getMyStore()
        setStore(storeResponse.data)

        // Fetch store stats
        const statsResponse = await storesAPI.getStats()
        setStats(statsResponse.data)
      } catch (error) {
        // 404 here means "this seller has no store yet" — a normal state the
        // page renders a setup prompt for, not an error worth surfacing.
        if (parseApiError(error).status === 404) {
          setStore(null)
        }
      }

      // Fetch products (seller's own products)
      try {
        const productsResponse = await productsAPI.sellerList()
        const allProducts =
          productsResponse.data.results || productsResponse.data || []
        setProducts(allProducts.slice(0, 5))
      } catch (error) {
        console.error('Error fetching products:', error)
      }

      // Fetch recent orders (seller orders)
      try {
        const ordersResponse = await ordersAPI.sellerList()
        const orders = ordersResponse.data.results || ordersResponse.data || []
        setRecentOrders(orders.slice(0, 5))
      } catch (error) {
        console.error('Error fetching orders:', error)
      }
    } catch (error) {
      console.error('Error fetching dashboard data:', error)
    } finally {
      setLoading(false)
    }
  }

  const StatCard = ({ icon: Icon, title, value, change, color = 'blue' }) => {
    const isPositive = change >= 0
    const colorClasses = {
      blue: 'from-blue-500 to-blue-600',
      green: 'from-green-500 to-green-600',
      purple: 'from-purple-500 to-purple-600',
      orange: 'from-orange-500 to-orange-600',
    }

    return (
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 hover:shadow-md transition-shadow">
        <div className="flex items-start justify-between mb-4">
          <div
            className={`p-3 rounded-lg bg-gradient-to-br ${colorClasses[color]} text-white`}
          >
            <Icon className="h-6 w-6" />
          </div>
          {change !== undefined && (
            <div
              className={`flex items-center gap-1 text-sm font-medium ${isPositive ? 'text-green-600' : 'text-red-600'}`}
            >
              {isPositive ? (
                <ArrowUpRight className="h-4 w-4" />
              ) : (
                <ArrowDownRight className="h-4 w-4" />
              )}
              {Math.abs(change).toFixed(1)}%
            </div>
          )}
        </div>
        <h3 className="text-sm font-medium text-gray-600 mb-1">{title}</h3>
        <p className="text-2xl font-bold text-gray-900">{value}</p>
        <p className="text-xs text-gray-500 mt-1">
          {t('dashboard.stats.vsPrevious')}
        </p>
      </div>
    )
  }

  const StatusBadge = ({ status, label }) => {
    const styles = {
      PENDING: 'bg-yellow-100 text-yellow-800 border-yellow-200',
      PROCESSING: 'bg-blue-100 text-blue-800 border-blue-200',
      COMPLETED: 'bg-green-100 text-green-800 border-green-200',
      SHIPPED: 'bg-purple-100 text-purple-800 border-purple-200',
      CANCELLED: 'bg-red-100 text-red-800 border-red-200',
    }

    return (
      <span
        className={`px-2 py-1 rounded-full text-xs font-medium border ${styles[status] || styles.PENDING}`}
      >
        {label || status}
      </span>
    )
  }

  if (authLoading || !isAuthenticated || !isSeller) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
      </div>
    )
  }

  // If seller doesn't have a store yet
  if (!loading && !store) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
        <div className="max-w-md w-full bg-white rounded-lg shadow-lg p-8 text-center">
          <div className="bg-primary/10 rounded-full p-4 w-20 h-20 mx-auto mb-4 flex items-center justify-center">
            <Store className="h-10 w-10 text-primary" />
          </div>
          <h2 className="text-2xl font-bold text-gray-900 mb-2">
            {t('dashboard.welcome.title')}
          </h2>
          <p className="text-gray-600 mb-6">{t('dashboard.welcome.body')}</p>
          <Link href="/seller/store/setup" className="btn-primary inline-block">
            {t('dashboard.welcome.cta')}
          </Link>
        </div>
      </div>
    )
  }

  // Calculate some dynamic stats
  const lowStockCount = stats?.low_stock_products || 0
  const pendingOrdersCount = stats?.pending_orders || 0
  const totalRevenue = stats?.total_revenue || 0
  const avgOrderValue = stats?.average_order_value || 0

  const alerts = []
  if (lowStockCount > 0) {
    alerts.push({
      type: 'warning',
      message: t('dashboard.alerts.lowStock', { count: lowStockCount }),
      action: t('dashboard.alerts.viewItems'),
      link: '/seller/products',
    })
  }
  if (pendingOrdersCount > 0) {
    alerts.push({
      type: 'info',
      message: t('dashboard.alerts.pending', { count: pendingOrdersCount }),
      action: t('dashboard.alerts.processOrders'),
      link: '/seller/orders',
    })
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-3">
                {store?.logo_url ? (
                  <img
                    src={store.logo_url}
                    alt={store.store_name}
                    className="h-10 w-10 rounded-lg object-cover"
                  />
                ) : (
                  <div className="h-10 w-10 rounded-lg bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-white font-bold text-lg">
                    {store?.store_name?.charAt(0).toUpperCase()}
                  </div>
                )}
                <div>
                  <h1 className="text-lg font-semibold text-gray-900">
                    {store?.store_name}
                  </h1>
                  <p className="text-xs text-gray-500">
                    {t('dashboard.subtitle')}
                  </p>
                </div>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <button
                aria-label={t('dashboard.notifications')}
                className="p-2 hover:bg-gray-100 rounded-lg relative"
              >
                <Bell className="h-5 w-5 text-gray-600" />
                {alerts.length > 0 && (
                  <span className="absolute top-1 end-1 h-2 w-2 bg-red-500 rounded-full"></span>
                )}
              </button>
              <Link
                href="/seller/store/setup"
                aria-label={t('dashboard.storeSettings')}
                className="p-2 hover:bg-gray-100 rounded-lg"
              >
                <Settings className="h-5 w-5 text-gray-600" />
              </Link>
              <Link
                href="/seller/products/create"
                className="px-4 py-2 bg-gradient-to-r from-blue-600 to-purple-600 text-white rounded-lg hover:from-blue-700 hover:to-purple-700 transition-all font-medium flex items-center gap-2"
              >
                <Plus className="h-4 w-4" />
                {t('dashboard.newProduct')}
              </Link>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Quick Filters */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setActiveTab('overview')}
              className={`px-4 py-2 rounded-lg font-medium transition-colors ${
                activeTab === 'overview'
                  ? 'bg-blue-600 text-white'
                  : 'bg-white text-gray-700 hover:bg-gray-50 border border-gray-200'
              }`}
            >
              {t('dashboard.tabs.overview')}
            </button>
            <button
              onClick={() => setActiveTab('products')}
              className={`px-4 py-2 rounded-lg font-medium transition-colors ${
                activeTab === 'products'
                  ? 'bg-blue-600 text-white'
                  : 'bg-white text-gray-700 hover:bg-gray-50 border border-gray-200'
              }`}
            >
              {t('dashboard.tabs.products')}
            </button>
            <button
              onClick={() => setActiveTab('orders')}
              className={`px-4 py-2 rounded-lg font-medium transition-colors ${
                activeTab === 'orders'
                  ? 'bg-blue-600 text-white'
                  : 'bg-white text-gray-700 hover:bg-gray-50 border border-gray-200'
              }`}
            >
              {t('dashboard.tabs.orders')}
            </button>
          </div>

          <select
            value={dateRange}
            onChange={(e) => setDateRange(e.target.value)}
            aria-label={t('dashboard.range.label')}
            className="px-4 py-2 bg-white border border-gray-200 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 cursor-pointer"
          >
            <option value="7d">{t('dashboard.range.last7')}</option>
            <option value="30d">{t('dashboard.range.last30')}</option>
            <option value="90d">{t('dashboard.range.last90')}</option>
            <option value="1y">{t('dashboard.range.lastYear')}</option>
          </select>
        </div>

        {/* Alerts Section */}
        {alerts.length > 0 && (
          <div className="mb-6 space-y-2">
            {alerts.map((alert, index) => (
              <div
                key={index}
                className={`flex items-center justify-between p-4 rounded-lg border ${
                  alert.type === 'warning'
                    ? 'bg-yellow-50 border-yellow-200'
                    : alert.type === 'info'
                      ? 'bg-blue-50 border-blue-200'
                      : 'bg-green-50 border-green-200'
                }`}
              >
                <div className="flex items-center gap-3">
                  <AlertCircle
                    className={`h-5 w-5 ${
                      alert.type === 'warning'
                        ? 'text-yellow-600'
                        : alert.type === 'info'
                          ? 'text-blue-600'
                          : 'text-green-600'
                    }`}
                  />
                  <span className="text-sm font-medium text-gray-900">
                    {alert.message}
                  </span>
                </div>
                <Link
                  href={alert.link}
                  className="text-sm font-medium text-blue-600 hover:text-blue-700"
                >
                  {alert.action}
                </Link>
              </div>
            ))}
          </div>
        )}

        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
            {[1, 2, 3, 4].map((i) => (
              <div
                key={i}
                className="bg-white p-6 rounded-lg shadow-sm border border-gray-200 animate-pulse"
              >
                <div className="h-8 bg-gray-300 rounded w-1/2 mb-4"></div>
                <div className="h-10 bg-gray-300 rounded w-3/4"></div>
              </div>
            ))}
          </div>
        ) : (
          <>
            {/* Stats Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
              <StatCard
                icon={DollarSign}
                title={t('dashboard.stats.revenue')}
                value={price(totalRevenue)}
                change={12.5}
                color="green"
              />
              <StatCard
                icon={ShoppingBag}
                title={t('dashboard.stats.orders')}
                value={stats?.total_orders || 0}
                change={8.3}
                color="blue"
              />
              <StatCard
                icon={Package}
                title={t('dashboard.stats.listed')}
                value={`${stats?.total_products || 0}/20`}
                change={4}
                color="purple"
              />
              <StatCard
                icon={TrendingUp}
                title={t('dashboard.stats.avgOrder')}
                value={price(avgOrderValue)}
                change={-0.5}
                color="orange"
              />
            </div>

            {/* Main Content Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Recent Orders - Takes 2 columns */}
              <div className="lg:col-span-2 bg-white rounded-xl shadow-sm border border-gray-200">
                <div className="p-6 border-b border-gray-200">
                  <div className="flex items-center justify-between">
                    <div>
                      <h2 className="text-lg font-semibold text-gray-900">
                        {t('dashboard.recentOrders.title')}
                      </h2>
                      <p className="text-sm text-gray-500 mt-1">
                        {t('dashboard.recentOrders.pendingCount', {
                          count: pendingOrdersCount,
                        })}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        aria-label={t('dashboard.recentOrders.search')}
                        className="p-2 hover:bg-gray-100 rounded-lg"
                      >
                        <Search className="h-4 w-4 text-gray-600" />
                      </button>
                      <button
                        aria-label={t('dashboard.recentOrders.filter')}
                        className="p-2 hover:bg-gray-100 rounded-lg"
                      >
                        <Filter className="h-4 w-4 text-gray-600" />
                      </button>
                      <Link
                        href="/seller/orders"
                        className="px-3 py-2 text-sm font-medium text-blue-600 hover:bg-blue-50 rounded-lg"
                      >
                        {t('dashboard.recentOrders.viewAll')}
                      </Link>
                    </div>
                  </div>
                </div>

                <div className="p-6">
                  {recentOrders.length === 0 ? (
                    <div className="text-center py-12 text-gray-500">
                      <ShoppingBag className="h-12 w-12 mx-auto mb-3 text-gray-400" />
                      <p>{t('dashboard.recentOrders.empty')}</p>
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {recentOrders.map((order) => (
                        <div
                          key={order.id}
                          className="flex items-center justify-between p-4 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors cursor-pointer"
                        >
                          <div className="flex items-center gap-4">
                            <div className="h-10 w-10 rounded-lg bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-white font-bold text-sm">
                              {order.items?.length || 1}
                            </div>
                            <div>
                              <div className="flex items-center gap-2 mb-1">
                                <p className="font-medium text-gray-900">
                                  #{order.id}
                                </p>
                                <StatusBadge
                                  status={order.order_status}
                                  label={
                                    order.order_status_label ||
                                    order.order_status
                                  }
                                />
                              </div>
                              <div className="flex items-center gap-3 text-sm text-gray-500">
                                <span className="flex items-center gap-1">
                                  <Calendar className="h-3 w-3" />
                                  {new Date(
                                    order.order_date
                                  ).toLocaleDateString()}
                                </span>
                              </div>
                            </div>
                          </div>
                          <div className="text-end">
                            <p className="font-semibold text-gray-900">
                              {price(order.total_amount)}
                            </p>
                            <Link
                              href={`/seller/orders/${order.id}`}
                              className="text-xs text-blue-600 hover:text-blue-700 font-medium mt-1"
                            >
                              {t('dashboard.recentOrders.viewDetails')}
                            </Link>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* Recent Products */}
              <div className="bg-white rounded-xl shadow-sm border border-gray-200">
                <div className="p-6 border-b border-gray-200">
                  <h2 className="text-lg font-semibold text-gray-900">
                    {t('dashboard.recentProducts.title')}
                  </h2>
                  <p className="text-sm text-gray-500 mt-1">
                    {t('dashboard.recentProducts.subtitle')}
                  </p>
                </div>

                <div className="p-6">
                  {products.length === 0 ? (
                    <div className="text-center py-8 text-gray-500">
                      <Package className="h-12 w-12 mx-auto mb-3 text-gray-400" />
                      <p className="mb-4">
                        {t('dashboard.recentProducts.empty')}
                      </p>
                      <Link
                        href="/seller/products/create"
                        className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
                      >
                        <Plus className="h-4 w-4" />
                        {t('dashboard.recentProducts.add')}
                      </Link>
                    </div>
                  ) : (
                    <div className="space-y-4">
                      {products.map((product, index) => (
                        <div
                          key={product.id}
                          className="flex items-start gap-3"
                        >
                          <div className="flex items-center justify-center h-8 w-8 rounded-lg bg-gradient-to-br from-blue-500 to-purple-600 text-white font-bold text-sm flex-shrink-0">
                            {index + 1}
                          </div>
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium text-gray-900 truncate">
                              {product.name}
                            </p>
                            <div className="flex items-center gap-2 mt-1">
                              <span className="text-xs font-semibold text-gray-900">
                                {price(product.base_price)}
                              </span>
                              <span
                                className={`text-xs px-2 py-0.5 rounded-full ${
                                  product.is_available
                                    ? 'bg-green-100 text-green-700'
                                    : 'bg-red-100 text-red-700'
                                }`}
                              >
                                {product.is_available
                                  ? t('dashboard.recentProducts.available')
                                  : t('dashboard.recentProducts.unavailable')}
                              </span>
                            </div>
                            <Link
                              href={`/products/${product.id}`}
                              className="text-xs text-blue-600 hover:text-blue-700 mt-1 inline-flex items-center gap-1"
                            >
                              <Eye className="h-3 w-3" />
                              {t('dashboard.recentProducts.view')}
                            </Link>
                          </div>
                        </div>
                      ))}
                      <Link
                        href="/seller/products"
                        className="block text-center text-sm font-medium text-blue-600 hover:text-blue-700 pt-2 border-t"
                      >
                        {t('dashboard.recentProducts.viewAll')}
                      </Link>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Quick Actions */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-6">
              <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-sm font-medium text-gray-600">
                    {t('dashboard.performance.title')}
                  </h3>
                  <BarChart3 className="h-5 w-5 text-gray-400" />
                </div>
                <p className="text-3xl font-bold text-gray-900 mb-2">
                  {(((stats?.active_products || 0) / 20) * 100).toFixed(0)}%
                </p>
                <div className="flex items-center gap-2">
                  <div className="flex-1 bg-gray-200 rounded-full h-2">
                    <div
                      className="bg-gradient-to-r from-green-500 to-green-600 h-2 rounded-full"
                      style={{
                        width: `${((stats?.active_products || 0) / 20) * 100}%`,
                      }}
                    ></div>
                  </div>
                  <span className="text-sm text-gray-600">
                    {stats?.active_products || 0}/20
                  </span>
                </div>
                <p className="text-xs text-gray-500 mt-2">
                  {t('dashboard.performance.active')}
                </p>
              </div>

              <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-sm font-medium text-gray-600">
                    {t('dashboard.performance.views')}
                  </h3>
                  <Eye className="h-5 w-5 text-gray-400" />
                </div>
                <p className="text-3xl font-bold text-gray-900 mb-2">
                  {((stats?.total_products || 0) * 87).toLocaleString()}
                </p>
                <div className="flex items-center gap-2">
                  <div className="flex-1 bg-gray-200 rounded-full h-2">
                    <div
                      className="bg-gradient-to-r from-blue-500 to-blue-600 h-2 rounded-full"
                      style={{ width: '78%' }}
                    ></div>
                  </div>
                  <span className="text-sm text-gray-600">78%</span>
                </div>
                <p className="text-xs text-gray-500 mt-2">
                  {t('dashboard.performance.engagement')}
                </p>
              </div>

              <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-sm font-medium text-gray-600">
                    {t('dashboard.performance.stockAlerts')}
                  </h3>
                  <AlertCircle className="h-5 w-5 text-yellow-500" />
                </div>
                <p className="text-3xl font-bold text-gray-900 mb-2">
                  {lowStockCount}
                </p>
                <Link
                  href="/seller/products"
                  className="text-sm font-medium text-blue-600 hover:text-blue-700 inline-flex items-center gap-1"
                >
                  {t('dashboard.performance.viewLowStock')}
                </Link>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
