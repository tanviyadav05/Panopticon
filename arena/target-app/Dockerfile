# --- build stage -----------------------------------------------------------
FROM golang:1.22-alpine AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -o /out/target-app .

# --- runtime stage -----------------------------------------------------------
FROM alpine:3.20
RUN adduser -D -u 10001 panopticon
WORKDIR /app
COPY --from=build /out/target-app .
RUN mkdir -p /app/data && \
    echo "Welcome to Project Panopticon's Arena." > /app/data/welcome.txt && \
    chown -R panopticon:panopticon /app
USER panopticon
ENV PORT=8080
EXPOSE 8080
ENTRYPOINT ["./target-app"]
