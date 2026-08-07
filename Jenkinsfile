// FRAME pipeline for the 2027 IAP Planning Module.
//
// FRAME's Jenkins triggers on `feature/all/<JIRA-TICKET>`. This file describes the
// stages; the job itself, the agent labels and the credential IDs are configured during
// FRAME onboarding and are the parts that cannot be verified outside the platform —
// treat the agent label and credentials below as placeholders to confirm on arrival.

pipeline {
    agent {
        label 'docker'
    }

    options {
        timestamps()
        buildDiscarder(logRotator(numToKeepStr: '30'))
        timeout(time: 30, unit: 'MINUTES')
        disableConcurrentBuilds(abortPrevious: true)
    }

    environment {
        PYTHON_VERSION = '3.11'
        NODE_VERSION   = '22'
        POETRY_VERSION = '2.3.3'
        // Ephemeral database for the build only. No deployed credential is ever read here.
        IAP_DATABASE_URL = 'postgresql+psycopg://iap:iap_ci@127.0.0.1:5432/iap'
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Backend') {
            stages {
                stage('Install') {
                    steps {
                        dir('backend') {
                            sh '''
                                pip install --user "poetry==${POETRY_VERSION}"
                                poetry config virtualenvs.in-project true --local
                                poetry install --no-interaction
                            '''
                        }
                    }
                }

                stage('Lint') {
                    steps {
                        dir('backend') {
                            sh 'poetry run ruff check .'
                        }
                    }
                }

                stage('Test') {
                    steps {
                        dir('backend') {
                            sh 'poetry run pytest --junitxml=reports/pytest.xml --cov=app --cov-report=xml'
                        }
                    }
                    post {
                        always {
                            junit allowEmptyResults: true, testResults: 'backend/reports/pytest.xml'
                        }
                    }
                }

                stage('Migrations') {
                    steps {
                        dir('backend') {
                            // Reversible, and matching the models. A model changed without a
                            // revision fails here rather than during a deployment window.
                            sh '''
                                poetry run alembic upgrade head
                                poetry run alembic downgrade base
                                poetry run alembic upgrade head
                                poetry run alembic check
                            '''
                        }
                    }
                }
            }
        }

        stage('Frontend') {
            stages {
                stage('Install') {
                    steps {
                        dir('frontend') {
                            sh 'npm ci'
                        }
                    }
                }

                stage('Typecheck') {
                    steps {
                        dir('frontend') {
                            sh 'npx tsc --noEmit'
                        }
                    }
                }

                stage('Test') {
                    steps {
                        dir('frontend') {
                            sh 'npm test -- --ci --reporters=default --reporters=jest-junit'
                        }
                    }
                    post {
                        always {
                            junit allowEmptyResults: true, testResults: 'frontend/junit.xml'
                        }
                    }
                }

                stage('Build') {
                    steps {
                        dir('frontend') {
                            sh 'npm run build'
                        }
                    }
                }
            }
        }

        stage('Images') {
            when {
                anyOf {
                    branch 'main'
                    branch pattern: 'feature/all/.*', comparator: 'REGEXP'
                }
            }
            steps {
                sh '''
                    docker build -t iap-planning-backend:${BUILD_NUMBER} ./backend
                    docker build -t iap-planning-frontend:${BUILD_NUMBER} ./frontend
                '''
            }
        }
    }

    post {
        always {
            cleanWs()
        }
    }
}
