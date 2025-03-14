import docker 
import logging 
import asyncio
logging.basicConfig(level=logging.INFO)
client = docker.from_env()


def create_container():
    logging.info('Building image...')
    client.images.build(path='.', tag='sandbox', dockerfile='Dockerfile.sandbox')

    logging.info('Running container with resource limits...')
    container = client.containers.run(
        "sandbox", 
        entrypoint='', 
        tty=True, # allocating a pseudo-TTY to keep the container alive
        detach=True,
        # Resource constraints
        mem_limit="4g",         # Limit memory to 4GB
        #memswap_limit="8g",     # Limit swap to same as memory (no swap)
        cpu_period=100_000,      # CPU period 100,000us
        cpu_quota=200_000,       # CPU quota 200,000us (2 cores = 200000/100000)
        cpu_shares=512          # CPU shares (relative weight) - this conatiner gets 512/1024 of the CPU time or about 50% as important
    )
    return container


async def main():
    container = create_container()

    new_container_handle = client.containers.get(container.id)

    logging.info('Executing command...')
    result = new_container_handle.exec_run('git --version')
    print(result.output)
    logging.info('Stopping container...')
    new_container_handle.stop()
    logging.info('Container stopped')

if __name__ == "__main__":
    asyncio.run(main()) 