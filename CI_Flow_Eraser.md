title AetherFlow CI/CD Pipeline
direction right

GitHub [icon: github] {
  Main Branch [icon: git-branch]
  Actions Workflow [icon: zap]
}

Quality Gates [icon: shield-check] {
  Django Tests [icon: check-square, label: "Job: Running Django Tests"]
  SonarCloud [icon: search, label: "Job: SonarCloud Scan"]
}

Cloud Deployment [icon: aws-cloud] {
  AWS Elastic Beanstalk [icon: aws-elastic-beanstalk, label: "Environment: AetherFlow-env"]
}

// Workflow Connections
Main Branch > Actions Workflow: Push / Pull Request
Actions Workflow > Django Tests: Trigger
Actions Workflow > SonarCloud: Trigger
Django Tests > AWS Elastic Beanstalk: Deploy (on success)
SonarCloud > GitHub: Annotate Pull Request
