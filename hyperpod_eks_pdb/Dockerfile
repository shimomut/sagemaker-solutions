FROM python:3

#RUN pip3 install debugpy
RUN pip3 install pdb-attach
#RUN pip3 install madbg

COPY ./debug_target.py /myapp/
COPY ./debug_tools.py /myapp/

CMD ["python3", "-u", "/myapp/debug_target.py"]
