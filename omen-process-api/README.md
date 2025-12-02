# Run env vars from heroku
heroku config:set $(cat .env | xargs) -a omeniq-process-api


# locally
docker run --env-file .env -p 5328:5328 your-image-name


heroku container:push web -a omeniq-process-api
heroku container:release web -a omeniq-process-api