#!/bin/bash
set -e

# Configuration
HARBOR_URL="harbor.uzhicai.com"
PROJECT="midtool"
IMAGE_NAME="db-monitor"
FULL_IMAGE="${HARBOR_URL}/${PROJECT}/${IMAGE_NAME}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}Database Monitor - Docker Build${NC}"
echo -e "${GREEN}================================${NC}"
echo ""

# Get version tag
if [ -z "$1" ]; then
    VERSION="latest"
    echo -e "${YELLOW}No version specified, using 'latest'${NC}"
else
    VERSION="$1"
    echo -e "${GREEN}Building version: ${VERSION}${NC}"
fi

# Full image tags
IMAGE_LATEST="${FULL_IMAGE}:latest"
IMAGE_VERSIONED="${FULL_IMAGE}:${VERSION}"

echo ""
echo -e "${GREEN}Step 1/5: Checking Docker login${NC}"
# Check if already logged in to Harbor
if ! docker info 2>/dev/null | grep -q "${HARBOR_URL}"; then
    echo -e "${YELLOW}Not logged in to Harbor, attempting login...${NC}"
    echo -e "${YELLOW}Please enter Harbor credentials:${NC}"
    docker login ${HARBOR_URL}
else
    echo -e "${GREEN}Already logged in to ${HARBOR_URL}${NC}"
fi

echo ""
echo -e "${GREEN}Step 2/5: Building Docker image${NC}"
docker build -t ${IMAGE_LATEST} -t ${IMAGE_VERSIONED} .

echo ""
echo -e "${GREEN}Step 3/5: Image build complete${NC}"
docker images | grep ${IMAGE_NAME} | head -5

echo ""
echo -e "${GREEN}Step 4/5: Pushing to Harbor${NC}"
echo -e "${YELLOW}Pushing ${IMAGE_LATEST}...${NC}"
docker push ${IMAGE_LATEST}

if [ "$VERSION" != "latest" ]; then
    echo -e "${YELLOW}Pushing ${IMAGE_VERSIONED}...${NC}"
    docker push ${IMAGE_VERSIONED}
fi

echo ""
echo -e "${GREEN}Step 5/5: Cleanup${NC}"
echo -e "${YELLOW}Cleaning up dangling images...${NC}"
docker image prune -f

echo ""
echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}Build and Push Complete!${NC}"
echo -e "${GREEN}================================${NC}"
echo ""
echo -e "Image URLs:"
echo -e "  ${GREEN}${IMAGE_LATEST}${NC}"
if [ "$VERSION" != "latest" ]; then
    echo -e "  ${GREEN}${IMAGE_VERSIONED}${NC}"
fi
echo ""
echo -e "To deploy on server:"
echo -e "  ${YELLOW}docker pull ${IMAGE_LATEST}${NC}"
echo -e "  ${YELLOW}docker run -d -p 5000:5000 -v /path/to/config.json:/app/config.json:ro ${IMAGE_LATEST}${NC}"
echo ""
echo -e "Or use docker-compose:"
echo -e "  ${YELLOW}docker-compose up -d${NC}"
echo ""
