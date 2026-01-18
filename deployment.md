# Commandos for DigitalOcean
# Build docker
'''
docker build --no-cache -t omeniq-crawl4ai:latest .
'''

# Remvoe image
docker image rm fe86

# Remove container
docker container rm 507

# 
docker logs omeniq-cralw4ai

docker inspect omeniq-cralw4ai | grep -A 5 "State"

docker restart omeniq-cralw4ai

docker exec omeniq-cralw4ai redis-cli ping

docker run -d --name omeniq-cralw4ai --shm-size=1g   -p 8080:8080   -e PORT=8080   -e API_KEY=2z04JzpI6gYHhK2FJb6L9zeWyVIkma0nxu77EtV2uHsxg   -e PLAYGROUND_ENABLED=false   omeniq-crawl4ai:latest