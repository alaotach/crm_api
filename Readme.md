# Customer Relationship Management API

A Customer Relationship Management (CRM) system built with FastAPI, Supabase, and JWT authentication.

## Features
- **Customer Management** - Create, update, delete, and view customers
- **Deal Pipeline** - Track deals like open, in progress or won/lose
- **Notes System** - Add notes to customers for better management and to remember things
- **Assignment System** - Assign customers and deals to sales reps

### Authentication
- **JWT Authentication** - jwt token based authentication
- **Custom Password Hashing** - SHA 256 with salt 6969 iterations hehe 
- **Role Based Access Control** - Admins, Managers, Sales Rep roles
- **Row-Level Security** - Users only see their assigned data

### Analytics
- **Deal Summaries** - Win rates, revenue metrics, pipeline analysis
- **Customer Value** - Track customer lifetime value and deal history
- **Team Performance** - Sales team leaderboards and metrics
- **Top Customers** - Revenue-based customer rankings

### Audit Logs
- Tracks all operations

### AI Features cuz i didnt know wht else to add
- **Motivational Quotes** - AI-generated sales motivation
- **Fun Facts** - Sales and business insights  
- **Email Generator** - Personalized sales email templates
- **Objection Handler** - AI assistance for handling customer objections
- **Meeting Prep** - Automated meeting preparation briefs

### Data Management
- **CSV/JSON Export** - Export customers, deals, and complete data
- **Bulk Import** - Import customers from CSV/JSON files
- **Data Validation** - Automatic data validation and error handling

## Tech Stack

- **Backend**: FastAPI
- **Database**: Supabase
- **Authentication**: JWT with custom hashing
- **AI**: ai api by hcb
- **Deployment**: nest by hcb

## Prerequisites

- Python 3.8+
- Supabase account
- ENV configured

## Installation

### 1. Clone the Repository
```bash
git clone https://github.com/alaotach/crm_api.git
cd crm
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Environment Setup
Create a `.env` file in the root directory:

```env
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_anon_key
JWT_KEY=your_jwt_token
```

### 4. Database Setup
Run the SQL script in your Supabase SQL Editor to create all tables:
check sql.md for table script


### 5. Run the Application
```bash
uvicorn main:app --reload
```

The API will be available at `http://localhost:8000`

## API Documentation

### Authentication Endpoints
```http
POST /auth/register     # register user
POST /auth/login        # login user
POST /auth/refresh      # refresh JWT token
POST /auth/change-password  # change password
GET  /auth/me          # get current user info
```

### Customer Management
```http
GET    /customers           # list all customers
POST   /customers           # create customer
GET    /customers/{id}      # get customer details
PUT    /customers/{id}      # update customer
DELETE /customers/{id}      # delete customer
PUT    /customers/{id}/assign  # assign customer to sales reps
```

### Deal Management
```http
GET    /deals              # list all deals
POST   /deals              # create deal
GET    /deals/{id}         # get deal details
PUT    /deals/{id}         # update deal
DELETE /deals/{id}         # delete deal
PUT    /deals/{id}/assign  # assign deal to sales reps
GET    /deals/pipeline     # get pipeline
```

### Notes
```http
POST   /customers/{id}/notes  # add note to customer
GET    /customers/{id}/notes  # get customer notes
GET    /notes              # list all notes
DELETE /notes/{id}         # delete a note
```

### Analytics
```http
GET /analytics/deals-summary     # deal metrics
GET /analytics/customer-value/{id}  # customer analysis
GET /analytics/top-customers     # leaderboard
GET /analytics/team-performance  # team performance
```

### User Management
```http
GET    /users              # list all users
GET    /users/{id}         # get user details
PUT    /users/{id}         # update user
DELETE /users/{id}         # delete user
GET    /users/{id}/dashboard   # dashboard
GET    /users/{id}/customers  # user's assigned customers
GET    /users/{id}/deals      # user's assigned deals
```

### Audit Logs
```http
GET /audit-logs                    # get audit logs with filters
GET /audit-logs/user/{user_id}     # user audit logs
GET /audit-logs/resource/{type}/{id}  # resource logs
```

### Data Export/Import
```http
GET  /export/customers?format=csv   # Export customers
GET  /export/deals?format=json      # Export deals
GET  /export/all                    # Export all data
POST /import/customers              # Import customers (CSV/JSON)
```

### AI Features
```http
GET  /motivation           # get motivational quote
GET  /fun-fact            # get sales fun fact
POST /generate-email      # generate emails
POST /ai/handle-objection # get help for handling objections
POST /meeting-prep        # generate prep brief
```


## User Roles

### Sales Rep
- View assigned customers and deals only
- Create/update own assigned records
- View personal dashboard and metrics
- Access to AI features and personal audit logs

### Manager
- View team data and performance
- Access to team analytics and reports
- View audit logs for team members
- Assign customers/deals to sales reps

### Admin
- Full system access
- User management capabilities
- Complete audit log access
- System configuration and maintenance

## Security Features

### Authentication
- JWT tokens with configurable expiration
- Custom password hashing (SHA-256 + salt)
- Secure password change functionality
- Request rate limiting ready

### Authorization
- Role-based access control (RBAC)
- Row-level security in database
- Resource ownership validation
- API endpoint protection

### Audit & Monitoring
- Complete audit trail for all operations
- IP address and user agent tracking
- Authentication event logging
- Failed login attempt tracking