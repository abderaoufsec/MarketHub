# MarketHub Backend Setup Guide

## Quick Start

### 1. Create Virtual Environment
```bash
python -m venv venv

# On Windows
venv\Scripts\activate

# On macOS/Linux
source venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Environment Configuration
Copy `.env.example` to `.env` and configure your settings:
```bash
cp .env.example .env
```

Update the following in your `.env` file:
- `SECRET_KEY`: Generate a new secret key
- Database credentials (DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT)
- Email settings for verification emails
- CORS_ALLOWED_ORIGINS (your frontend URL)

### 4. Database Setup

Make sure PostgreSQL is installed and running, then create the database:
```bash
createdb markethub_db
```

Run migrations:
```bash
python manage.py makemigrations
python manage.py migrate
```

### 5. Create Superuser
```bash
python manage.py createsuperuser
```

### 6. Run Development Server
```bash
python manage.py runserver
```

The API will be available at `http://localhost:8000`

## API Documentation

Once running, access API documentation at:
- Swagger UI: http://localhost:8000/api/docs/
- ReDoc: http://localhost:8000/api/redoc/

## Project Structure

```
backend/
├── core/                  # Django project settings
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── apps/                  # Django applications
│   ├── users/            # User authentication & profiles
│   ├── stores/           # Store management
│   ├── products/         # Product catalog
│   ├── inventory/        # Stock tracking
│   ├── orders/           # Order processing
│   └── payments/         # Payment handling
├── manage.py
└── requirements.txt
```

## Key Features

### Authentication
- JWT-based authentication with HttpOnly cookies
- Email verification required
- Role-based access (Buyer/Seller)

### API Endpoints

#### Authentication (`/api/auth/`)
- POST `/register/` - User registration
- POST `/login/` - User login
- POST `/logout/` - User logout
- GET `/verify-email/<token>/` - Email verification
- GET `/profile/` - Get user profile
- PUT `/profile/` - Update profile
- POST `/change-password/` - Change password

#### Stores (`/api/stores/`)
- GET `/` - List all stores
- GET `/<slug>/` - Get store details
- POST `/seller/create/` - Create store (sellers only)
- GET `/seller/my-store/` - Get own store
- PUT `/seller/my-store/` - Update own store
- GET `/seller/stats/` - Store statistics

#### Products (`/api/products/`)
- GET `/` - List products (with search/filter)
- GET `/<id>/` - Get product details
- POST `/` - Create product (sellers only)
- PUT `/<id>/` - Update product
- DELETE `/<id>/` - Delete product

#### Orders (`/api/orders/`)
- GET `/` - List user orders
- POST `/checkout/` - Create order
- GET `/<id>/` - Order details

### Security Features
- HTTPS enforced in production
- CORS protection
- CSRF protection
- Password validation
- SQL injection protection
- XSS protection via HttpOnly cookies

## Testing

Run tests:
```bash
python manage.py test
```

## Deployment

### Production Settings
1. Set `DEBUG=False`
2. Update `ALLOWED_HOSTS`
3. Configure proper database credentials
4. Set up email backend (SMTP)
5. Use environment variables for secrets

### Static Files
```bash
python manage.py collectstatic
```

### Recommended Hosting
- Backend: Render.com, Railway.app, or PythonAnywhere
- Database: Neon, Supabase, or managed PostgreSQL
- Static Files: WhiteNoise (included) or CDN

## Troubleshooting

### Database Connection Issues
- Verify PostgreSQL is running
- Check database credentials in `.env`
- Ensure database exists: `createdb markethub_db`

### Migration Issues
```bash
python manage.py makemigrations
python manage.py migrate --run-syncdb
```

### Port Already in Use
```bash
python manage.py runserver 8001
```

## Support
For issues, refer to:
- Django documentation: https://docs.djangoproject.com/
- DRF documentation: https://www.django-rest-framework.org/
