FROM eclipse-temurin:21-jdk-jammy

RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-pil curl ca-certificates gnupg \
 && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && npm install -g @anthropic-ai/claude-code \
 && apt-get clean

WORKDIR /mcsre
COPY bots/package.json bots/package-lock.json bots/
RUN cd bots && npm ci --no-audit --no-fund --silent
COPY . .
RUN python3 -m mcsre setup

ENTRYPOINT ["python3", "-m", "mcsre"]
CMD ["demo"]
