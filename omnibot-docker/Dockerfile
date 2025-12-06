# Use a lightweight web server (Nginx)
FROM nginx:alpine

# Copy your bot interface to the server's public folder
# Ensure 'index.html' (previously memory_bot.html) is in the same folder as this Dockerfile
COPY index.html /usr/share/nginx/html/index.html

# Expose port 80 (internal)
EXPOSE 80