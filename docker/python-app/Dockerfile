# Use an official Python runtime as a parent image
FROM python:3

# Set the working directory in the container to /app
WORKDIR /app

# Copy only the requirements.txt file into the container at /app
COPY requirements.txt /app/

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application's source code into the container at /app
COPY . /app
