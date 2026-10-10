export default function SkeletonLoader({ variant = 'default', count = 1 }) {
  const variants = {
    default: 'h-4 rounded skeleton',
    card: (
      <div className="card p-4 space-y-4">
        <div className="h-48 rounded skeleton" />
        <div className="space-y-2">
          <div className="h-4 rounded skeleton w-3/4" />
          <div className="h-4 rounded skeleton w-1/2" />
        </div>
        <div className="h-8 rounded skeleton" />
      </div>
    ),
    product: (
      <div className="bg-white rounded-lg shadow-sm overflow-hidden">
        <div className="h-48 bg-gray-200 skeleton" />
        <div className="p-4 space-y-3">
          <div className="h-5 rounded skeleton w-3/4" />
          <div className="h-4 rounded skeleton w-1/2" />
          <div className="flex justify-between items-center">
            <div className="h-6 rounded skeleton w-20" />
            <div className="h-8 w-8 rounded-full skeleton" />
          </div>
        </div>
      </div>
    ),
    text: 'h-4 rounded skeleton',
    avatar: 'h-12 w-12 rounded-full skeleton',
    button: 'h-10 rounded skeleton w-24',
  }

  if (variant === 'card' || variant === 'product') {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {Array.from({ length: count }).map((_, i) => (
          <div key={i}>{variants[variant]}</div>
        ))}
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className={variants[variant]} />
      ))}
    </div>
  )
}
