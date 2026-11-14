# The toy village's Geni module: the provider and the project its profiles join. The rest of this
# directory is what `verso generate-tf` writes.
terraform {
  required_providers {
    geni = {
      source = "dmalch/genealogy"
    }
  }
}

data "geni_project" "stepanchikovo" {
  project_id = "project-0"
}
