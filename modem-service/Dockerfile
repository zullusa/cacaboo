# syntax=docker/dockerfile:1

FROM golang:1.22-alpine AS build

WORKDIR /src

COPY go.mod go.sum ./
RUN go mod download

COPY . .

RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /out/modem-service .

FROM alpine:3.20

RUN apk add --no-cache ca-certificates tzdata

COPY --from=build /out/modem-service /usr/local/bin/modem-service

EXPOSE 8004

ENTRYPOINT ["/usr/local/bin/modem-service"]