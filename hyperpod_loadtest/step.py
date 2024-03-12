import os
import time
import random
import logging
import concurrent.futures


class Config:
    
    #logging_method = "print"
    #logging_method = "print_with_flush"
    logging_method = "logging_to_separate_files"

    num_logging_processes = 1000
    num_logging_lines_per_process = 10


class App:

    @staticmethod
    def init_worker():
        print("Initializing worker process")


    @staticmethod
    def test_logging(job_id):
        
        slurm_node_id = os.environ["SLURM_NODEID"]

        if Config.logging_method=="logging_to_separate_files":
            os.makedirs("output/separate", exist_ok=True)
            logging.basicConfig(filename=f"output/separate/log_{slurm_node_id}_{job_id}.txt", level=logging.DEBUG)

        i = 0
        while True:
            if Config.logging_method=="print":
                print(f"test_logging slurm_node_id={slurm_node_id}, job_id={job_id}, i={i}")
            elif Config.logging_method=="print_with_flush":
                print(f"test_logging slurm_node_id={slurm_node_id}, job_id={job_id}, i={i}", flush=True)
            elif Config.logging_method=="logging_to_separate_files":
                logging.info(f"test_logging slurm_node_id={slurm_node_id}, job_id={job_id}, i={i}")
            time.sleep(0.01)

            if i>=Config.num_logging_lines_per_process:
                break

            i+=1

        return i


    def main(self):

        input_logging = range(Config.num_logging_processes)

        t0 = time.time()

        pool_executer_logging = concurrent.futures.ProcessPoolExecutor(
            max_workers=Config.num_logging_processes, 
            initializer=App.init_worker, 
            initargs=[]
        )

        map_result = pool_executer_logging.map(
            App.test_logging,
            input_logging
        )

        map_result = list(map_result)
        assert len(map_result)==len(input_logging)

        t1 = time.time()

        total_num_log_lines = sum(map_result)
        print(f"Num lines wrote : {total_num_log_lines}")
        print(f"Time spent : {t1-t0}")
        print(f"Line per second  : {total_num_log_lines /(t1-t0)}")



if __name__ == "__main__":
    app = App()
    app.main()
    