#  OBJECT ORIENTED PROGRAMMING (OOP) PROJECT BY OYIBO, NUHU OJOCHOGWU
# FACULTY: FOUNDATION IN DATA SCIENCE
# PROJECT: VEHICLE RENTAL SYSTEM.
# Objective: Build a vehicle rental system that allows customers to rent and return different types of vehicles. 
# Required Features; Your system should allow users to: 
# 1.  Register customers
# 2.  Add vehicles
# 3.  Display available vehicles 
# 4.  Rent a vehicle
# 5.  Return a vehicle 
# 6.  Calculate rental costs 
# 7.  Display rental history 
# 8   Display currently rented vehicles 
# 9.  Search for vehicles
# 10. Prevent unavailable vehicles from being rented 
# 11. Calculate the total rental cost
# 12. Prevent invalid rental periods

# Vehicle Rental System — Python OOP Project

from datetime import datetime
from math import isfinite

# VEHICLE CLASS
# -------------

class Vehicle:
    def __init__(self, vehicle_id, brand, model, year, daily_rate):
        self.vehicle_id = vehicle_id
        self.brand = brand
        self.model = model
        self.year = year
        self.__daily_rate = daily_rate
        self.__is_available = True

# Encapsulation: getter for daily rate. Protectect the daily rate from being modified directly. That is, the daily rate can only be set when the vehicle is created and cannot be changed later.

    def get_daily_rate(self):
        return self.__daily_rate

# Encapsulation: vehicle availability

    def is_available(self):
        return self.__is_available

    def rent_vehicle(self):
        if not self.__is_available:
            raise ValueError("Vehicle is already rented.")

        self.__is_available = False
        return "Vehicle status changed to Rented."

    def return_vehicle(self):
        if self.__is_available:
            raise ValueError("Vehicle is already available.")

        self.__is_available = True
        return "Vehicle status changed to Available."

# Polymorphic method. Helps calculate the rental cost based on the vehicle type and rental days. Each subclass (Car, Motorcycle, Truck) will override this method to provide specific calculations.

    def calculate_rental_cost(self, days):
        return self.__daily_rate * days

    def vehicle_type(self):
        return "Vehicle"

    def get_details(self):
        status = "Available" if self.__is_available else "Rented"

        return (
            f"ID: {self.vehicle_id} | "
            f"Type: {self.vehicle_type()} | "
            f"Brand: {self.brand} | "
            f"Model: {self.model} | "
            f"Year: {self.year} | "
            f"Daily Rate: ₦{self.get_daily_rate():,.2f} | "
            f"Status: {status}")


# CAR CLASS
#-----------

class Car(Vehicle):
    SPEED_LIMIT_KMH = 100

    def __init__(self, vehicle_id, brand, model, year):
        super().__init__(vehicle_id, brand, model, year, 10000)

    def get_speed_limit(self):
        return self.SPEED_LIMIT_KMH

# Polymorphism

    def calculate_rental_cost(self, days):
        return 10000 * days

    def vehicle_type(self):
        return "Car"


# MOTORCYCLE CLASS
# ----------------

class Motorcycle(Vehicle):
    def __init__(self, vehicle_id, brand, model, year):
        super().__init__(vehicle_id, brand, model, year, 5000)

# Polymorphism

    def calculate_rental_cost(self, days):
        return 5000 * days

    def vehicle_type(self):
        return "Motorcycle"


# TRUCK CLASS
# -----------

class Truck(Vehicle):
    def __init__(self, vehicle_id, brand, model, year):
        super().__init__(vehicle_id, brand, model, year, 20000)

# Polymorphism
    def calculate_rental_cost(self, days):
        return 20000 * days

    def vehicle_type(self):
        return "Truck"


# CUSTOMER CLASS
# --------------

class Customer:
    def __init__(self, customer_id, name, phone, email):
        self.customer_id = customer_id
        self.name = name
        self.phone = phone
        self.email = email

# Customer's rental history

        self.__rental_history = []

# Encapsulation

    def add_rental_history(self, rental):
        self.__rental_history.append(rental)

    def get_rental_history(self):
        return self.__rental_history.copy()

    def get_details(self):
        return (f"Customer ID: {self.customer_id} | "
            f"Name: {self.name} | "
            f"Phone: {self.phone} | "
            f"Email: {self.email}")


# RENTAL CLASS
# ------------

class Rental:
    def __init__(self, rental_id, customer, vehicle, rental_days, mileage, security_deposit=50000):
        if rental_days <= 0:
            raise ValueError("Rental period must be greater than zero.")

        if mileage < 0:
            raise ValueError("Mileage cannot be negative.")

        self.rental_id = rental_id
        self.customer = customer
        self.vehicle = vehicle
        self.rental_days = rental_days
        self.mileage = mileage
        self.security_deposit = security_deposit

        self.late_days = 0
        self.is_returned = False
        self.final_cost = 0
        self.tracking_history = []

# Calculate cost when rental is created

        self.base_cost = vehicle.calculate_rental_cost(rental_days)

    def update_tracking(self, location, speed_kmh):
        if self.is_returned:
            raise ValueError("Tracking is unavailable for a returned rental.")

        if not isinstance(self.vehicle, Car):
            raise ValueError("Tracking and speed limits are available for car rentals only.")

        if not isinstance(location, str) or not location.strip():
            raise ValueError("Location cannot be empty.")

        if not isinstance(speed_kmh, (int, float)) or not isfinite(speed_kmh) or speed_kmh < 0:
            raise ValueError("Speed must be a finite, non-negative number.")

        update = {
            "timestamp": datetime.now(),
            "location": location.strip(),
            "speed_kmh": speed_kmh,
            "over_speed_limit": speed_kmh > self.vehicle.get_speed_limit(),
        }
        self.tracking_history.append(update)

        if update["over_speed_limit"]:
            return (
                f"Speed warning: {speed_kmh:.1f} km/h exceeds the "
                f"{self.vehicle.get_speed_limit()} km/h limit."
            )

        return f"Tracking update recorded at {update['timestamp']:%Y-%m-%d %H:%M:%S}."

    def get_tracking_details(self):
        if not isinstance(self.vehicle, Car):
            raise ValueError("Tracking is available for car rentals only.")

        if not self.tracking_history:
            return (
                f"No tracking updates recorded. Speed limit: "
                f"{self.vehicle.get_speed_limit()} km/h."
            )

        details = [
            f"Speed limit: {self.vehicle.get_speed_limit()} km/h",
            "Tracking history:",
        ]
        for update in self.tracking_history:
            status = "SPEED LIMIT EXCEEDED" if update["over_speed_limit"] else "Within limit"
            details.append(
                f"{update['timestamp']:%Y-%m-%d %H:%M:%S} | "
                f"Location: {update['location']} | "
                f"Speed: {update['speed_kmh']:.1f} km/h | {status}"
            )

        return "\n".join(details)

# DISCOUNT
# --------

    def calculate_discount(self):
        """
        Discount rules:
        7 - 13 days  = 5%
        14 - 29 days = 10%
        30+ days     = 15%
        """

        if self.rental_days >= 30:
            return self.base_cost * 0.15

        elif self.rental_days >= 14:
            return self.base_cost * 0.10

        elif self.rental_days >= 7:
            return self.base_cost * 0.05

        return 0

    
# MILEAGE CHARGE
# --------------

    def calculate_mileage_charge(self):
        """
        First 100 km are free.

        Additional mileage:
        Car        = ₦100 per km
        Motorcycle = ₦50 per km
        Truck      = ₦200 per km
        """

        free_mileage = 100

        if self.mileage <= free_mileage:
            return 0

        extra_mileage = self.mileage - free_mileage

        if isinstance(self.vehicle, Car):
            return extra_mileage * 100

        elif isinstance(self.vehicle, Motorcycle):
            return extra_mileage * 50

        elif isinstance(self.vehicle, Truck):
            return extra_mileage * 200

        return 0

    
# LATE RETURN CHARGE
# ------------------

    def calculate_late_charge(self):
        """
        Late return charge is 20% of the vehicle's
        daily rate for every late day.
        """

        if self.late_days <= 0:
            return 0

        return (self.vehicle.get_daily_rate() * 0.20 * self.late_days)

    
# TOTAL RENTAL COST
# -----------------

    def calculate_total_cost(self):
        discount = self.calculate_discount()
        mileage_charge = self.calculate_mileage_charge()
        late_charge = self.calculate_late_charge()

        rental_cost_after_discount = (self.base_cost - discount)

        self.final_cost = (rental_cost_after_discount + mileage_charge + late_charge + self.security_deposit)

        return self.final_cost

    
# RETURN VEHICLE
# --------------

    def return_rental(self, actual_days, actual_mileage=None):
        if self.is_returned:
            raise ValueError("This rental has already been returned.")

        if actual_days <= 0:
            raise ValueError(
                "Actual rental period must be greater than zero.")

        if actual_mileage is not None:
            if actual_mileage < 0:
                raise ValueError("Mileage cannot be negative.")

            self.mileage = actual_mileage

# Determine whether the vehicle was returned late

        if actual_days > self.rental_days:
            self.late_days = actual_days - self.rental_days

        self.vehicle.return_vehicle()
        self.is_returned = True

        return self.calculate_total_cost()

    
# RENTAL INFORMATION
# -------------------

    def get_details(self):
        status = "Returned" if self.is_returned else "Currently Rented"

        return (
            f"Rental ID: {self.rental_id} | "
            f"Customer: {self.customer.name} | "
            f"Vehicle: {self.vehicle.brand} "
            f"{self.vehicle.model} | "
            f"Days: {self.rental_days} | "
            f"Mileage: {self.mileage} km | "f"Status: {status} | " f"Total: ₦{self.calculate_total_cost():,.2f}")



# RENTAL SYSTEM CLASS
# -------------------

class RentalSystem:
    def __init__(self):

# Dictionaries make searching by ID easier

        self.__vehicles = {}
        self.__customers = {}
        self.__rentals = {}


# CUSTOMER MANAGEMENT
# -------------------

    def register_customer(self, customer_id, name, phone, email):
        if customer_id in self.__customers:
            raise ValueError("A customer with this ID already exists.")

        if not name.strip():
            raise ValueError("Customer name cannot be empty.")

        customer = Customer(customer_id, name, phone, email)

        self.__customers[customer_id] = customer

        return customer

# CUSTOMER ID
# -----------

    def generate_next_id(self):
        return str(len(self.__customers) + 1).zfill(3)

# An old customer renting again doesn't register a new customer,
# so their rental ID is generated from the rental count instead.

    def generate_next_rental_id(self):
        return "R" + str(len(self.__rentals) + 1).zfill(3)

    def find_customer(self, customer_id):
        customer = self.__customers.get(customer_id)

        if customer is None:
            raise ValueError("Customer not found.")

        return customer

    
# VEHICLE MANAGEMENT
# ------------------

    def add_vehicle(self, vehicle):
        if vehicle.vehicle_id in self.__vehicles:
            raise ValueError("A vehicle with this ID already exists.")

        self.__vehicles[vehicle.vehicle_id] = vehicle

        return (f"{vehicle.vehicle_type()} " f"{vehicle.brand} {vehicle.model} added successfully.")


# DISPLAY AVAILABLE VEHICLES
# --------------------------

    def display_available_vehicles(self):
        available = []

        for vehicle in self.__vehicles.values():
            if vehicle.is_available():
                available.append(vehicle.get_details())

        if not available:
            return "No vehicles are currently available."

        return "\n".join(available)

    
# VEHICLE AVAILABILITY BY BRAND AND YEAR
# --------------------------------------

    def find_available_vehicle(self, vehicle_type, brand, year):
        for vehicle in self.__vehicles.values():

            if (vehicle.vehicle_type().lower() == vehicle_type.lower() and vehicle.brand.lower() == brand.lower() and vehicle.year == year and vehicle.is_available()):
                return vehicle

        return None


# CHECK VEHICLE AVAILABILITY
# --------------------------

    def check_vehicle_availability(self, vehicle_id, vehicle_type, brand, year):
        vehicle = self.__vehicles.get(vehicle_id)

        if vehicle is None:
            return f"No vehicle found with ID {vehicle_id}."

# Confirm the details entered actually match this vehicle

        matches = (vehicle.vehicle_type().lower() == vehicle_type.lower() and vehicle.brand.lower() == brand.lower() and vehicle.year == year)

        if not matches:
            return "No vehicle matches that Type, Brand, Year and ID combination."

        status = "Available" if vehicle.is_available() else "Not Available"

        return (f"{vehicle.get_details()}\n"f"This vehicle is currently: {status}")


# SEARCH VEHICLES
# ---------------

    def search_vehicles(self, search_term):
        search_term = search_term.lower()
        results = []

        for vehicle in self.__vehicles.values():

            if (search_term in vehicle.brand.lower() or search_term in vehicle.model.lower() or search_term in vehicle.vehicle_type().lower() or search_term in vehicle.vehicle_id.lower()):
                results.append(vehicle.get_details())

        if not results:
            return "No vehicles matched your search."

        return "\n".join(results)

    
# RENT VEHICLE
# ------------

    def rent_vehicle(self, rental_id, customer_id, vehicle_id, rental_days, mileage):
        if rental_id in self.__rentals:
            raise ValueError("A rental with this ID already exists.")

        customer = self.find_customer(customer_id)

        vehicle = self.__vehicles.get(vehicle_id)

        if vehicle is None:
            raise ValueError("Vehicle not found.")

# Prevent unavailable vehicle from being rented

        if not vehicle.is_available():
            raise ValueError("This vehicle is currently rented" "and cannot be rented again.")

# Prevent invalid rental periods

        if rental_days <= 0:
            raise ValueError("Rental period must be greater than zero.")

        if mileage < 0:
            raise ValueError("Mileage cannot be negative.")

# Change vehicle status from Available -> Rented

        vehicle.rent_vehicle()

        rental = Rental(rental_id,customer,vehicle,rental_days, mileage)

        self.__rentals[rental_id] = rental

# Add rental to customer's history
        
        customer.add_rental_history(rental)

        return (f"Vehicle rented successfully.\n"f"Rental ID: {rental_id}\n"f"Customer: {customer.name}\n"f"Vehicle: {vehicle.brand} {vehicle.model}\n"f"Rental period: {rental_days} days\n"f"Estimated total: "f"₦{rental.calculate_total_cost():,.2f}")


# RETURN VEHICLE
# --------------

    def return_vehicle(self, rental_id, actual_days, actual_mileage=None):

        rental = self.__rentals.get(rental_id)

        if rental is None:
            raise ValueError("Rental not found.")

        if rental.is_returned:
            raise ValueError("This vehicle has already been returned.")

        if actual_days <= 0:
            raise ValueError("Actual rental period must be greater than zero.")

        total_cost = rental.return_rental(actual_days, actual_mileage)

        return (f"Vehicle returned successfully.\n"f"Vehicle: {rental.vehicle.brand}"f"{rental.vehicle.model}\n"f"Late days: {rental.late_days}\n"f"Final rental cost: ₦{total_cost:,.2f}")


# RENTAL HISTORY
# --------------

    def display_rental_history(self):
        if not self.__rentals:
            return "No rental history available."

        history = []

        for rental in self.__rentals.values():
            history.append(rental.get_details())

        return "\n".join(history)

    
# SINGLE RENTAL DETAILS
# ---------------------

    def get_rental_details(self, rental_id):
        rental = self.__rentals.get(rental_id)

        if rental is None:
            raise ValueError("Rental not found.")

        return rental.get_details()

    def track_rental(self, rental_id, location, speed_kmh):
        rental = self.__rentals.get(rental_id)

        if rental is None:
            raise ValueError("Rental not found.")

        return rental.update_tracking(location, speed_kmh)

    def get_rental_tracking(self, rental_id):
        rental = self.__rentals.get(rental_id)

        if rental is None:
            raise ValueError("Rental not found.")

        return rental.get_tracking_details()

# CURRENTLY RENTED VEHICLES
# --------------------------

    def display_currently_rented(self):
        rented = []

        for rental in self.__rentals.values():

            if not rental.is_returned:
                rented.append(rental.vehicle.get_details())

        if not rented:
            return "No vehicles are currently rented."

        return "\n".join(rented)

    
# CUSTOMER RENTAL HISTORY
# -----------------------

    def customer_rental_history(self, customer_id):

        customer = self.find_customer(customer_id)

        history = customer.get_rental_history()

        if not history:
            return (f"{customer.name} has no rental history.")
        return "\n".join(rental.get_details() for rental in history)


# RENTAL COST
# -----------

    def calculate_rental_cost(self, rental_id):

        rental = self.__rentals.get(rental_id)

        if rental is None:
            raise ValueError("Rental not found.")

        return rental.calculate_total_cost()


# SYSTEM SUMMARY
# --------------

    def system_summary(self):

        total_vehicles = len(self.__vehicles)
        total_customers = len(self.__customers)
        total_rentals = len(self.__rentals)

        available = 0
        rented = 0

        for vehicle in self.__vehicles.values():

            if vehicle.is_available():
                available += 1
            else:
                rented += 1

        return (f"Total Vehicles: {total_vehicles}\n"f"Available Vehicles: {available}\n"f"Currently Rented: {rented}\n"f"Registered Customers: {total_customers}\n"f"Total Rentals: {total_rentals}")


# INPUT HELPER FUNCTIONS
# ----------------------

def get_positive_integer(message):
    while True:
        try:
            value = int(input(message))

            if value <= 0:
                raise ValueError

            return value

        except ValueError:
            return "Invalid input. Please enter a positive number."


def get_non_negative_float(message):
    while True:
        try:
            value = float(input(message))

            if value < 0:
                raise ValueError

            return value

        except ValueError:
            return "Invalid input. Please enter a valid number."



# SAMPLE SYSTEM OBJECT
# --------------------

rental_system = RentalSystem()



# ADD DIFFERENT VEHICLES
# ----------------------

car1 = Car("C001","Toyota","Camry",2024)

car2 = Car("C002","Honda","Accord",2023)

motorcycle1 = Motorcycle("M001","Honda","CBR",2024)

motorcycle2 = Motorcycle("M002","Yamaha","MT-07",2023)

truck1 = Truck("T001","Mercedes","Actros",2022)

truck2 = Truck("T002","Volvo","FH16",2023)

rental_system.add_vehicle(car1)
rental_system.add_vehicle(car2)
rental_system.add_vehicle(motorcycle1)
rental_system.add_vehicle(motorcycle2)
rental_system.add_vehicle(truck1)
rental_system.add_vehicle(truck2)



# REGISTER CUSTOMERS
# ------------------

customer1 = rental_system.register_customer("CU001","Oyibo Maya","08039378598","9uoyibo@gmail.com")

customer2 = rental_system.register_customer("CU002","Mary Smith","08073354545","augu6t9u@yahoo.com")


# WELCOME MESSAGE
# ---------------

print("Welcome to Oyibo's Rentals")

# MAIN MENU
# ---------

print("\nWhat would you like to do?")
print("1. Rentals      - Rent a vehicle")
print("2. Return       - Return a rented vehicle")
print("3. Availability - Check available vehicles")
print("4. Track car    - Record a rented car's location and speed")

menu_choice = input("Enter your choice (1, 2, 3 or 4): ")

# OPTION 1: RENTALS
# -----------------

if menu_choice == "1":

    print("\nAre you a new customer or an old customer?")
    print("1. New Customer")
    print("2. Old Customer")

    customer_type = input("Enter your choice (1 or 2): ")


# OLD (ALREADY REGISTERED) CUSTOMER
# ---------------------------------

    if customer_type == "2":

        print("\nAvailable Vehicles")
        print(rental_system.display_available_vehicles())

        existing_customer_id = input("Enter your Customer ID (e.g. CU001): ")

        try:
            existing_customer = rental_system.find_customer(existing_customer_id)

        except ValueError as error:
            print(error)

        else:
            input_vehicle_type = input("Enter type of car (e.g. Car, Motorcycle or Truck): ")
            input_brand = input("Enter brand (e.g. Toyota): ")
            input_year = int(input("Enter year (e.g. 2024): "))
            input_rental_days = int(input("How many days do you want to rent for (e.g. 5): "))

            matched_vehicle = rental_system.find_available_vehicle(input_vehicle_type, input_brand, input_year)

            if matched_vehicle is None:
                print("Sorry, no available vehicle matches that request.")

            else:
                estimated_cost = matched_vehicle.calculate_rental_cost(input_rental_days)

                print(f"Estimated rental cost for {input_rental_days} day(s): ₦{estimated_cost:,.2f}")

                payment_confirmation = input("Proceed with payment? (yes/no): ")

                if payment_confirmation.strip().lower() == "yes":
                    new_rental_id = rental_system.generate_next_rental_id()

                    rental_result = rental_system.rent_vehicle(new_rental_id, existing_customer_id, matched_vehicle.vehicle_id, input_rental_days, 0)

                    rental_summary = rental_system.get_rental_details(new_rental_id)

                    print(rental_summary)

                else:
                    print("Payment not completed.")
   
# NEW CUSTOMER
# ------------

    else:

        print("\nAvailable Vehicles")
        print(rental_system.display_available_vehicles())

        customer_name = input("Enter your name (e.g. Kunle Caleb): ")
        input_vehicle_type = input("Enter type of car (e.g. Car, Motorcycle or Truck): ")
        input_brand = input("Enter brand (e.g. Toyota): ")
        input_year = int(input("Enter year (e.g. 2024): "))
        input_rental_days = int(input("How many days do you want to rent for (e.g. 5): "))

        matched_vehicle = rental_system.find_available_vehicle(input_vehicle_type, input_brand, input_year)

        if matched_vehicle is None:
            print("Sorry, no available vehicle matches that request.")

        else:
            estimated_cost = matched_vehicle.calculate_rental_cost(input_rental_days)

            print(f"Estimated rental cost for {input_rental_days} day(s): ₦{estimated_cost:,.2f}")

            payment_confirmation = input("Proceed with payment? (yes/no): ")

# A new customer is only added to the system once payment succeeds

            if payment_confirmation.strip().lower() == "yes":
                next_id_number = rental_system.generate_next_id()
                new_customer_id = "CU" + next_id_number
                new_rental_id = "R" + next_id_number

                customer = rental_system.register_customer(new_customer_id, customer_name, "N/A", "N/A")

                rental_result = rental_system.rent_vehicle(new_rental_id, new_customer_id, matched_vehicle.vehicle_id, input_rental_days, 0)

                rental_summary = rental_system.get_rental_details(new_rental_id)

                print(rental_summary)

            else:
                print("Payment not completed. Customer was not registered.")



# OPTION 2: RETURN
# -----------------

elif menu_choice == "2":

    print("\nReturn a Rented Vehicle")

    return_rental_id = input("Enter your Rental ID (e.g. R001): ")

    try:
        input_actual_days = int(input("Enter actual number of days rented (e.g. 5): "))
        input_actual_mileage = int(input("Enter actual mileage driven in km (e.g. 250): "))

        return_result = rental_system.return_vehicle(return_rental_id, actual_days=input_actual_days, actual_mileage=input_actual_mileage)

    except ValueError as error:
        print(error)

    else:
        rental_summary = rental_system.get_rental_details(return_rental_id)
        print(rental_summary)


# OPTION 3: AVAILABILITY
# ----------------------

elif menu_choice == "3":

    print("\nAvailable Vehicles")
    print(rental_system.display_available_vehicles())

elif menu_choice == "4":

    print("\nTrack a Rented Car")
    tracking_rental_id = input("Enter the Rental ID (e.g. R001): ")

    try:
        tracking_location = input("Enter the current location: ")
        tracking_speed = float(input("Enter the current speed in km/h: "))
        tracking_result = rental_system.track_rental(
            tracking_rental_id, tracking_location, tracking_speed)

    except ValueError as error:
        print(error)

    else:
        print(tracking_result)
        print(rental_system.get_rental_tracking(tracking_rental_id))

else:
    print("Invalid selection. Please enter 1, 2, 3 or 4.")