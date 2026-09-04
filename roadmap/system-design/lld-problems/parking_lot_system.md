
# Parking Lot System

## Description

A **parking lot** is a dedicated area intended for parking vehicles. Parking lots are present in every city and suburban area.

Locations like **shopping malls, stadiums, airports, and train stations** often feature parking lots with large capacity.

A parking lot can:
- Spread across multiple buildings with multiple floors
- Be a large open area

### Supported Vehicle Types

The parking lot allows the following vehicle types:

- **Motorcycles / Scooters**
- **Cars / SUVs**
- **Buses / Trucks**

### Parking Spots

- Each vehicle occupies **one parking spot**
- Spot size differs based on **vehicle type**
- The number of spots varies per parking lot

Example:

| Vehicle Type | Spots |
|---|---|
| Motorcycles / Scooters | 100 |
| Cars / SUVs | 80 |
| Buses / Trucks | 40 |

### Parking Flow

When a vehicle is parked:

A **parking ticket** is generated containing:

- Spot number
- Entry date-time

When a vehicle is unparked:

A **parking receipt** is generated containing:

- Entry date-time
- Exit date-time
- Applicable parking fees

---

# Fee Models

Different locations have different fee models.

## Mall Parking

**Per-hour flat fee**

| Vehicle | Fee per hour |
|---|---|
| Motorcycle | 10 |
| Car / SUV | 20 |
| Bus / Truck | 50 |

---

## Stadium Parking

Flat rate up to certain intervals, then increasing rates.

The **total fee is the sum of all previous intervals**.

No parking spots for **buses/trucks**.

| Vehicle | Interval | Fee |
|---|---|---|
| Motorcycle | [0,4) hours | 30 |
| Motorcycle | [4,12) hours | 60 |
| Motorcycle | [12,∞) hours | 100 per hour |
| Car / SUV | [0,4) hours | 60 |
| Car / SUV | [4,12) hours | 120 |
| Car / SUV | [12,∞) hours | 200 per hour |

**Notation rule**:
- Start times = **inclusive**
- End times = **exclusive**

---

## Airport Parking

Flat rate for the first day, then **per-day rate afterwards**.

Previous interval fees are **not summed**.

No parking spots for **buses/trucks**.

### Motorcycle

| Interval | Fee |
|---|---|
| [0,1) hours | Free |
| [1,8) hours | 40 |
| [8,24) hours | 60 |
| Each additional day | 80 |

### Car / SUV

| Interval | Fee |
|---|---|
| [0,12) hours | 60 |
| [12,24) hours | 80 |
| Each additional day | 100 |

Notation rules:
- Start times = **inclusive**
- End times = **exclusive**

---

# Problem Statement

Given a parking lot with:

- Vehicle types supported
- Number of spots
- Fee model

Compute the **parking fees** when the vehicle is unparked.

---

# Example 1 — Small Motorcycle Parking Lot

### Spots

- Motorcycles / Scooters: **2 spots**
- Cars / SUVs / Trucks: **Not available**

Fee Model: **Mall model**

### Scenarios

| Sr No | Action | Result |
|---|---|---|
| 1 | Park motorcycle | Ticket 001, Spot 1 |
| 2 | Park scooter | Ticket 002, Spot 2 |
| 3 | Park scooter | No space available |
| 4 | Unpark scooter (002) | Fee: 10 |
| 5 | Park motorcycle | Ticket 003, Spot 2 |
| 6 | Unpark motorcycle (001) | Fee: 40 |

---

# Example 2 — Mall Parking Lot

### Spots

- Motorcycles / Scooters: **100**
- Cars / SUVs: **80**
- Buses / Trucks: **10**

### Scenarios

- Motorcycle parked **3 hours 30 mins** → Fee **40**
- Car parked **6 hours 1 min** → Fee **140**
- Truck parked **1 hour 59 mins** → Fee **100**

---

# Example 3 — Stadium Parking Lot

### Spots

- Motorcycles / Scooters: **1000**
- Cars / SUVs: **1500**

### Scenarios

- Motorcycle parked **3h 40m** → Fee **30**

- Motorcycle parked **14h 59m** → Fee **390**
  - 30 for first 4 hours
  - 60 for next 8 hours
  - 300 for remaining duration

- Electric SUV parked **11h 30m** → Fee **180**
  - 60 for first 4 hours
  - 120 for remaining duration

- SUV parked **13h 5m** → Fee **580**
  - 60 for first 4 hours
  - 120 for next 8 hours
  - 400 for remaining duration

---

# Example 4 — Airport Parking Lot

### Spots

- Motorcycles / Scooters: **200**
- Cars / SUVs: **500**
- Buses / Trucks: **100**

### Scenarios

- Motorcycle parked **55 mins** → Fee **0**
- Motorcycle parked **14h 59m** → Fee **60**
- Motorcycle parked **1 day 12 hours** → Fee **160**
- Car parked **50 mins** → Fee **60**
- SUV parked **23h 59m** → Fee **80**
- Car parked **3 days 1 hour** → Fee **400**
