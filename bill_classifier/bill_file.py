class BillFile:
    file_name: str
    bill_owner: str
    bill_type: str

    def __init__(self, file_name, bill_owner, bill_type):
        self.file_name = file_name
        self.bill_owner = bill_owner
        self.bill_type = bill_type

