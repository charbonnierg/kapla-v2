docker:
	docker buildx build --platform linux/armv7 -f Dockerfile --tag quara/k:latest --push .
