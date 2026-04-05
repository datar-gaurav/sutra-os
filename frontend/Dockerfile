FROM node:20-alpine

RUN apk add --no-cache curl bash

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

COPY . .

# Create non-root user
RUN addgroup -S sutra && adduser -S sutra -G sutra \
    && chown -R sutra:sutra /app

# Make entrypoint executable
RUN chmod +x start.sh

USER sutra

EXPOSE 3001
ENTRYPOINT ["./start.sh"]
