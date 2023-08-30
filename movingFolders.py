#%% Step I: Initial configuration
import boto3
import json

# Autentication config
session = boto3.Session(
    aws_access_key_id='your_aws_access_key_id',
    aws_secret_access_key='your_aws_secret_access_key',
    aws_session_token='your_aws_session_token',
    region_name='the_region_where_the_QuickSight_folders_are'
)

# Init QS resources
quicksight = session.client('quicksight')

# AWS account ID
aws_account_id = 'your_aws_account_id'

#%% Step II: Build the structure to be copied
def has_subfolders(folder_arn):
    response = quicksight.search_folders(
        AwsAccountId=aws_account_id,
        Filters=[
            {
                'Name': 'PARENT_FOLDER_ARN',
                'Operator': 'StringEquals',
                'Value': folder_arn
            }
        ]
    )
    return response['FolderSummaryList']

def get_folder_content(folder_id, content_type):
    response = quicksight.list_folder_members(
        AwsAccountId=aws_account_id,
        FolderId=folder_id
    )

    content = []
    for member in response['FolderMemberList']:
        if content_type in member['MemberArn']:
            content.append({"MemberId": member['MemberId']})
    return content

def create_json(folders):
    return [
        {
            "Arn": folder["Arn"],
            "FolderId": folder["FolderId"],
            "Name": folder["Name"]
        }
        for folder in folders
    ]

def build_folder_structure(folder, sub_folders):
    folder_structure = {
        "Arn": folder["Arn"],
        "FolderId": folder["FolderId"],
        "Name": folder["Name"],
        "Analyses": get_folder_content(folder['FolderId'], 'analysis'),
        "Dashboards": get_folder_content(folder['FolderId'], 'dashboard'),
        "Datasets": get_folder_content(folder['FolderId'], 'dataset'),
        "Subfolders": []
    }

    for sub_folder in sub_folders:
        subfolder_structure = build_folder_structure(sub_folder, has_subfolders(sub_folder['Arn']))
        folder_structure["Subfolders"].append(subfolder_structure)

    return folder_structure

def add_folder_content(folders):
    for idx, folder in enumerate(folders):
        sub_folders = has_subfolders(folder['Arn'])
        modified_folder = build_folder_structure(folder, sub_folders)
        folders[idx] = modified_folder

def adjust_folder_structure(folders):
    folder_ids = set(folder["FolderId"] for folder in folders)
    subfolder_ids = set(subfolder["FolderId"] for folder in folders for subfolder in folder.get("Subfolders", []))

    for folder in folders:
        if folder["FolderId"] in subfolder_ids:
            folder["Subfolders"] = adjust_folder_structure(folder["Subfolders"])
    
    adjusted_folders = [folder for folder in folders if folder["FolderId"] not in subfolder_ids]

    return adjusted_folders

#%% Step III: List all folders and their contents
all_folders = quicksight.list_folders(AwsAccountId=aws_account_id).get('FolderSummaryList')
all_folders = create_json(all_folders)

add_folder_content(all_folders)
all_folders = adjust_folder_structure(all_folders)

json_output = json.dumps(all_folders, indent=4)
print(json_output)

''' expected output:
[
    {
        "Arn": "folder_arn",
        "FolderId": "folder_id",
        "Name": "folder_name",
        "Analyses": [ //if there is any analysis, it will appear here
            {
                "MemberId": "folder_analysis_1"
            },
            {
                "MemberId": "folder_analysis_2"
            }
        ],
        "Dashboards": [ //if there is any dashboard, it will appear here
            {
                "MemberId": "folder_dashboard_1"
            },
            {
                "MemberId": "folder_dashboard_2"
            }
        ],
        "Datasets": [ //if there is any dataset, it will appear here
            {
                "MemberId": "folder_dataset_1"
            },
            {
                "MemberId": "folder_dataset_2"
            }
        ],
        "Subfolders": [ //if there is any subolder, the same structure for the analyses, dashboards and datasets are built
            {
                "Arn": "subfolder_arn",
                "FolderId": "subfolder_id",
                "Name": "sufolder_name",
                "Analyses": [
                    {
                        "MemberId": "subfolder_anaysis_1"
                    },
                    {
                        "MemberId": "subfolder_anaysis_2"
                    }
                ],
                "Dashboards": [
                    {
                        "MemberId": "subfolder_dashboard_1"
                    },
                    {
                        "MemberId": "subfolder_dashboard_2"
                    }
                ],
                "Datasets": [
                    {
                        "MemberId": "subfolder_dataset_1"
                    },
                    {
                        "MemberId": "subfolder_dataset_2"
                    }
                ],
                "Subfolders": [ //in case the subfolder has a subfolder, we keep the same structure
                ]
            },
            ... //for other subolders
        ]
    },
    ... //for other folders
]
'''

#%% Step IV: Remove the folders that you don't want to move
not_moving_folder_ids = ["FolderId_1", "FolderId_2", "FolderId_3"] #add, if needed, the other folder ids in this array

moving_folders = [folder for folder in all_folders if folder["FolderId"] not in not_moving_folder_ids]

json_output_moving_folders = json.dumps(moving_folders, indent=4)
print(json_output_moving_folders)

#%% STEP V: Copying content
def create_folder_and_members(aws_account_id, folder, parent_folder_arn):
    # recreate the actual folder
    new_folder = quicksight.create_folder(
        AwsAccountId=aws_account_id,
        Name=folder['Name'],
        FolderId='DestinationFolder' + folder['Name'].replace(' ', '').replace('[', '').replace(']', ''),
        ParentFolderArn=parent_folder_arn
    )
    new_folder_arn = new_folder['Arn']
    new_folder_id = new_folder['FolderId']

    # check if there's any analysis and, if there is, adds it
    if 'Analyses' in folder:
        for analysis in folder['Analyses']:
            quicksight.create_folder_membership(
                AwsAccountId=aws_account_id,
                FolderId=new_folder_id,
                MemberId=analysis['MemberId'],
                MemberType="ANALYSIS"
            )

    # check if there's any dashbaord and, if there is, adds it
    if 'Dashboards' in folder:
        for dashboard in folder['Dashboards']:
            quicksight.create_folder_membership(
                AwsAccountId=aws_account_id,
                FolderId=new_folder_id,
                MemberId=dashboard['MemberId'],
                MemberType="DASHBOARD"
            )

    # check if there's any dataset and, if there is, adds it
    if 'Datasets' in folder:
        for dataset in folder['Datasets']:
            quicksight.create_folder_membership(
                AwsAccountId=aws_account_id,
                FolderId=new_folder_id,
                MemberId=dataset['MemberId'],
                MemberType="DATASET"
            )

    # check if there's any subfolder and, if there is, call the function recursively
    if 'Subfolders' in folder:
        for subfolder in folder['Subfolders']:
            create_folder_and_members(aws_account_id, subfolder, new_folder_arn)

#%% Step VI: Finally executing
target_folder_arn = "arn_of_DestinationFolder" #the arn of your destination folder comes here

for folder in moving_folders: #moving_folders is the json we created at Step IV
    create_folder_and_members(aws_account_id, folder, target_folder_arn)
