image = {
  image = "localhost:5000/temporal-worker:test-terraform"
}
channel = "1.0/edge"

config = {
  namespace = "default"
  queue     = "test-queue"
}
