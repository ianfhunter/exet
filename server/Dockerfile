FROM node:22-alpine

WORKDIR /app

COPY package.json ./
COPY server.js ./

ENV PORT=3080
ENV SAVE_DIR=/data/puzzles
ENV STATIC_DIR=/static

EXPOSE 3080

CMD ["node", "server.js"]
