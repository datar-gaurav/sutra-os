FROM node:20-alpine

RUN apk add --no-cache curl bash

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

COPY . .

# Make entrypoint executable
RUN chmod +x start.sh

EXPOSE 3001
ENTRYPOINT ["./start.sh"]
