docker:
	docker buildx build --platform linux/amd64 -f Dockerfile --tag quara.azurecr.io/k:latest --push .
