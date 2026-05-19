#!/usr/bin/env bash

# =========================================================================================
# Enterprise GCP Cloud Run Global Application Load Balancer & SSL Setup Script
# =========================================================================================
# This script automates the provisioning of a Global External Application Load Balancer
# with Serverless NEGs, Google-managed SSL certificates, and HTTP-to-HTTPS redirects.
#
# It supports the following workflows:
#   1. Creating a brand new shared Load Balancer (for the first environment).
#   2. Viewing details of an existing Load Balancer (Frontends, IPs, SSL certs, and Backend routing rules).
#   3. Adding a new environment/subdomain to an existing shared Load Balancer.
#   4. Modifying existing configurations (Updating SSL certificates, changing fallback backends, or cleanups).
# =========================================================================================

set -euo pipefail

# ANSI color codes for premium terminal output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color
CLEAR='\033[0m'

echo -e "${BLUE}======================================================================${CLEAR}"
echo -e "${BLUE}   Enterprise GCP Global Load Balancer & SSL Manager                  ${CLEAR}"
echo -e "${BLUE}======================================================================${CLEAR}"

# 1. Validation & Inputs
if ! command -v gcloud &> /dev/null; then
    echo -e "${RED}Error: 'gcloud' CLI is not installed.${CLEAR}"
    echo -e "Please install the Google Cloud SDK: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# Ensure user is logged in
CURRENT_USER=$(gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>/dev/null || true)
if [ -z "$CURRENT_USER" ]; then
    echo -e "${YELLOW}Warning: No active gcloud session detected.${CLEAR}"
    echo -e "Please log in by running: ${GREEN}gcloud auth login${CLEAR}"
    exit 1
fi

# Prompt for GCP Project
read -p "Enter your GCP Project ID: " GCP_PROJECT_ID
if [ -z "$GCP_PROJECT_ID" ]; then
    echo -e "${RED}Project ID cannot be empty.${CLEAR}"
    exit 1
fi

echo -e "\n${BLUE}Verifying connection and setting project to '$GCP_PROJECT_ID'...${CLEAR}"
gcloud config set project "$GCP_PROJECT_ID" --quiet

# 2. Select Operation Mode
echo -e "\n${YELLOW}Choose the operation mode:${CLEAR}"
echo -e "  [1] Create a brand new shared Load Balancer"
echo -e "  [2] View / Manage / Update an existing shared Load Balancer"
read -p "Enter selection [1 or 2, default: 1]: " OP_MODE
OP_MODE=${OP_MODE:-1}

# Initialize URL MAP variable
URL_MAP_NAME="fastapi-global-alb"

if [ "$OP_MODE" = "2" ]; then
    echo -e "\n${BLUE}Querying existing Global Load Balancers (URL Maps) in project '$GCP_PROJECT_ID'...${CLEAR}"
    EXISTING_MAPS=$(gcloud compute url-maps list --global --format="value(name)" 2>/dev/null || true)
    
    if [ -z "$EXISTING_MAPS" ]; then
        echo -e "${YELLOW}No global Load Balancers (URL Maps) found in this project. Switching to Create Mode.${CLEAR}"
        OP_MODE=1
    else
        echo -e "${GREEN}Available Global Load Balancers:${CLEAR}"
        map_array=()
        i=1
        while read -r map; do
            [ -z "$map" ] && continue
            echo -e "  [$i] $map"
            map_array+=("$map")
            i=$((i+1))
        done <<< "$EXISTING_MAPS"
        
        read -p "Select a Load Balancer by number (1-$((i-1))) or enter name: " MAP_SELECTION
        if [[ "$MAP_SELECTION" =~ ^[0-9]+$ ]] && [ "$MAP_SELECTION" -ge 1 ] && [ "$MAP_SELECTION" -lt "$i" ]; then
            URL_MAP_NAME="${map_array[$((MAP_SELECTION-1))]}"
        else
            URL_MAP_NAME=${MAP_SELECTION:-"fastapi-global-alb"}
        fi
        
        # Display existing load balancer configuration details
        echo -e "\n${BLUE}======================================================================${CLEAR}"
        echo -e "${GREEN}   LOAD BALANCER CONFIGURATION DETAILS FOR: $URL_MAP_NAME${CLEAR}"
        echo -e "${BLUE}======================================================================${CLEAR}"
        
        # A. Display Backends (Backend Services & NEGs)
        echo -e "\n${YELLOW}--- Backends (Backend Services) ---${CLEAR}"
        DEFAULT_BE=$(gcloud compute url-maps describe "$URL_MAP_NAME" --global --format="value(defaultService)" 2>/dev/null | awk -F/ '{print $NF}' || true)
        PATH_BEs=$(gcloud compute url-maps describe "$URL_MAP_NAME" --global --format="value(pathMatchers[].defaultService)" 2>/dev/null | tr ';' '\n' | awk -F/ '{print $NF}' | sort -u || true)
        
        if [ -n "$DEFAULT_BE" ]; then
            echo -e "  - ${BLUE}$DEFAULT_BE${CLEAR} (Default Fallback Service)"
        fi
        for be in $PATH_BEs; do
            if [ "$be" != "$DEFAULT_BE" ] && [ -n "$be" ]; then
                echo -e "  - ${BLUE}$be${CLEAR}"
            fi
        done
        
        # B. Display Host Routing Rules
        echo -e "\n${YELLOW}--- Host Routing Rules (Domain -> Path Matcher) ---${CLEAR}"
        gcloud compute url-maps describe "$URL_MAP_NAME" --global --format="table(hostRules[].hosts[].join(','):label=HOSTS, hostRules[].pathMatcher:label=PATH_MATCHER)" 2>/dev/null || echo -e "  No host rules configured (default routing only)."
        
        # C. Display Frontends (HTTPS Forwarding Rules, Target Proxies, SSL Certificates, IPs)
        echo -e "\n${YELLOW}--- Frontends (HTTPS / Port 443) ---${CLEAR}"
        PROXIES=$(gcloud compute target-https-proxies list --global --filter="urlMap ~ $URL_MAP_NAME" --format="value(name)" 2>/dev/null || true)
        if [ -z "$PROXIES" ]; then
            echo -e "  No active HTTPS target proxies found pointing to this Load Balancer."
        else
            while read -r proxy; do
                [ -z "$proxy" ] && continue
                echo -e "  ${YELLOW}Proxy:${CLEAR} $proxy"
                # Get SSL certs
                certs=$(gcloud compute target-https-proxies describe "$proxy" --global --format="value(sslCertificates)" 2>/dev/null | tr ',' ' ' || true)
                echo -e "    ${YELLOW}SSL Certificates:${CLEAR} $certs"
                # Get forwarding rules
                rules_info=$(gcloud compute forwarding-rules list --global --filter="target ~ $proxy" --format="value(name, IPAddress, portRange)" 2>/dev/null || true)
                if [ -z "$rules_info" ]; then
                    echo -e "    ${RED}No active forwarding rule pointing to this proxy.${CLEAR}"
                else
                    while read -r rname rip rport; do
                        [ -z "$rname" ] && continue
                        echo -e "    ${YELLOW}Forwarding Rule:${CLEAR} $rname | ${BLUE}IP:${CLEAR} $rip | ${BLUE}Port:${CLEAR} $rport"
                    done <<< "$rules_info"
                fi
            done <<< "$PROXIES"
        fi
        echo -e "${BLUE}======================================================================${CLEAR}"
        
        # Prompt for actions on this load balancer
        echo -e "\n${YELLOW}Select action for '$URL_MAP_NAME':${CLEAR}"
        echo -e "  [1] Add a new routing rule (Create a new environment frontend/backend & subdomain)"
        echo -e "  [2] Update/Modify existing frontend SSL Certificate"
        echo -e "  [3] Set/Change Load Balancer default fallback backend service"
        echo -e "  [4] Remove an environment's routing rules (Host Rule + Path Matcher) from this Load Balancer"
        read -p "Enter selection [1-4, default: 1]: " OP_ACTION
        OP_ACTION=${OP_ACTION:-1}
        
        # Process OP_ACTION updates
        if [ "$OP_ACTION" = "2" ]; then
            echo -e "\n${BLUE}--- SSL Certificate Updater ---${CLEAR}"
            read -p "Enter the Target HTTPS Proxy name to update: " PROXY_TO_UPDATE
            if [ -z "$PROXY_TO_UPDATE" ]; then
                echo -e "${RED}Proxy name cannot be empty.${CLEAR}"
                exit 1
            fi
            read -p "Enter the new domain name for the SSL certificate (e.g. api.theashish.space): " NEW_SSL_DOMAIN
            if [ -z "$NEW_SSL_DOMAIN" ]; then
                echo -e "${RED}Domain name cannot be empty.${CLEAR}"
                exit 1
            fi
            
            # Replace characters in domain to generate cert name
            CLEAN_DOMAIN=${NEW_SSL_DOMAIN//./-}
            NEW_SSL_CERT_NAME="fastapi-cert-${CLEAN_DOMAIN}-$(date +%s)"
            
            echo -e "\n${YELLOW}Creating new Google-Managed SSL Certificate '$NEW_SSL_CERT_NAME'...${CLEAR}"
            gcloud compute ssl-certificates create "$NEW_SSL_CERT_NAME" \
                --domains="$NEW_SSL_DOMAIN" \
                --global \
                --quiet
                
            echo -e "${YELLOW}Binding SSL Certificate to Target HTTPS Proxy '$PROXY_TO_UPDATE'...${CLEAR}"
            gcloud compute target-https-proxies update "$PROXY_TO_UPDATE" \
                --ssl-certificates="$NEW_SSL_CERT_NAME" \
                --global \
                --quiet
                
            echo -e "${GREEN}✓ SSL Certificate updated successfully for proxy '$PROXY_TO_UPDATE'!${CLEAR}"
            echo -e "It can take up to 72 hours for the certificate to validate and provision."
            exit 0
            
        elif [ "$OP_ACTION" = "3" ]; then
            echo -e "\n${BLUE}--- Fallback Backend Modifier ---${CLEAR}"
            read -p "Enter the new default Backend Service name: " NEW_BACKEND_SERVICE
            if [ -z "$NEW_BACKEND_SERVICE" ]; then
                echo -e "${RED}Backend service name cannot be empty.${CLEAR}"
                exit 1
            fi
            
            echo -e "\n${YELLOW}Updating fallback backend service of '$URL_MAP_NAME' to '$NEW_BACKEND_SERVICE'...${CLEAR}"
            gcloud compute url-maps set-default-service "$URL_MAP_NAME" \
                --default-service="$NEW_BACKEND_SERVICE" \
                --global \
                --quiet
                
            echo -e "${GREEN}✓ Fallback backend updated successfully!${CLEAR}"
            exit 0
            
        elif [ "$OP_ACTION" = "4" ]; then
            echo -e "\n${BLUE}--- Routing Rule Cleanup ---${CLEAR}"
            read -p "Enter the host domain to remove (e.g. stage.theashish.space): " HOST_TO_REMOVE
            if [ -z "$HOST_TO_REMOVE" ]; then
                echo -e "${RED}Host domain cannot be empty.${CLEAR}"
                exit 1
            fi
            read -p "Enter the path matcher name to remove (e.g. pm-fastapi-stage): " PATH_MATCHER_TO_REMOVE
            if [ -z "$PATH_MATCHER_TO_REMOVE" ]; then
                echo -e "${RED}Path matcher name cannot be empty.${CLEAR}"
                exit 1
            fi
            
            echo -e "\n${YELLOW}Removing Host Rule '$HOST_TO_REMOVE' from '$URL_MAP_NAME'...${CLEAR}"
            gcloud compute url-maps remove-host-rule "$URL_MAP_NAME" \
                --host="$HOST_TO_REMOVE" \
                --global \
                --quiet || echo -e "${YELLOW}Host rule not found or already removed.${CLEAR}"
                
            echo -e "${YELLOW}Removing Path Matcher '$PATH_MATCHER_TO_REMOVE' from '$URL_MAP_NAME'...${CLEAR}"
            gcloud compute url-maps remove-path-matcher "$URL_MAP_NAME" \
                --path-matcher-name="$PATH_MATCHER_TO_REMOVE" \
                --global \
                --quiet || echo -e "${YELLOW}Path matcher not found or already removed.${CLEAR}"
                
            echo -e "${GREEN}✓ Cleanup completed!${CLEAR}"
            exit 0
        fi
    fi
fi

# Ask for the creation/adding configurations
if [ "$OP_MODE" = "1" ]; then
    read -p "Enter Load Balancer URL Map name [default: fastapi-global-alb]: " URL_MAP_NAME
    URL_MAP_NAME=${URL_MAP_NAME:-fastapi-global-alb}
fi

read -p "Enter Cloud Run service name for this environment (e.g. fastapi-dev): " RUN_SERVICE
if [ -z "$RUN_SERVICE" ]; then
    echo -e "${RED}Cloud Run service name cannot be empty.${CLEAR}"
    exit 1
fi

read -p "Enter preferred GCP region [default: asia-south1]: " GCP_REGION
GCP_REGION=${GCP_REGION:-asia-south1}

read -p "Enter custom domain to map for this environment (e.g. dev.theashish.space): " CUSTOM_DOMAIN
if [ -z "$CUSTOM_DOMAIN" ]; then
    echo -e "${RED}Custom domain cannot be empty.${CLEAR}"
    exit 1
fi

# Define idempotent naming conventions
IP_NAME="fastapi-ip-$RUN_SERVICE"
NEG_NAME="fastapi-neg-$RUN_SERVICE"
BACKEND_NAME="fastapi-backend-$RUN_SERVICE"
SSL_CERT_NAME="fastapi-cert-$RUN_SERVICE"
REDIRECT_MAP_NAME="fastapi-redirect-map-$RUN_SERVICE"
HTTPS_PROXY_NAME="fastapi-https-proxy-$RUN_SERVICE"
HTTP_PROXY_NAME="fastapi-http-proxy-$RUN_SERVICE"
HTTPS_FORWARDING_RULE="fastapi-https-rule-$RUN_SERVICE"
HTTP_FORWARDING_RULE="fastapi-http-rule-$RUN_SERVICE"

# 3. Enable APIs
echo -e "\n${YELLOW}Step 1: Enabling Compute Engine APIs...${CLEAR}"
gcloud services enable compute.googleapis.com --quiet
echo -e "${GREEN}✓ Compute Engine API enabled successfully!${CLEAR}"

# 4. Reserve Static External IP
echo -e "\n${YELLOW}Step 2: Reserving Global Static External IP Address...${CLEAR}"
if gcloud compute addresses describe "$IP_NAME" --global &>/dev/null; then
    echo -e "${BLUE}Static IP '$IP_NAME' already exists.${CLEAR}"
else
    gcloud compute addresses create "$IP_NAME" \
        --global \
        --ip-version=IPV4 \
        --quiet
    echo -e "${GREEN}✓ Global static IP '$IP_NAME' reserved!${CLEAR}"
fi
ALB_IP=$(gcloud compute addresses describe "$IP_NAME" --global --format="value(address)")
echo -e "${GREEN}Reserved IP Address: $ALB_IP${CLEAR}"

# 5. Create Serverless NEG
echo -e "\n${YELLOW}Step 3: Creating Serverless Network Endpoint Group (NEG)...${CLEAR}"
if gcloud compute network-endpoint-groups describe "$NEG_NAME" --region="$GCP_REGION" &>/dev/null; then
    echo -e "${BLUE}Serverless NEG '$NEG_NAME' already exists in $GCP_REGION.${CLEAR}"
else
    gcloud compute network-endpoint-groups create "$NEG_NAME" \
        --region="$GCP_REGION" \
        --network-endpoint-type=serverless \
        --cloud-run-service="$RUN_SERVICE" \
        --quiet
    echo -e "${GREEN}✓ Serverless NEG '$NEG_NAME' created successfully!${CLEAR}"
fi

# 6. Create Backend Service
echo -e "\n${YELLOW}Step 4: Provisioning Backend Service...${CLEAR}"
if gcloud compute backend-services describe "$BACKEND_NAME" --global &>/dev/null; then
    echo -e "${BLUE}Backend Service '$BACKEND_NAME' already exists.${CLEAR}"
else
    gcloud compute backend-services create "$BACKEND_NAME" \
        --global \
        --load-balancing-scheme=EXTERNAL_MANAGED \
        --quiet
    echo -e "${GREEN}✓ Backend Service '$BACKEND_NAME' created!${CLEAR}"
fi

# 7. Attach Serverless NEG Backend
echo -e "\n${YELLOW}Step 5: Attaching Serverless NEG to Backend Service...${CLEAR}"
if gcloud compute backend-services describe "$BACKEND_NAME" --global --format="value(backends)" | grep -q "$NEG_NAME" 2>/dev/null; then
    echo -e "${BLUE}NEG '$NEG_NAME' already attached to Backend Service.${CLEAR}"
else
    gcloud compute backend-services add-backend "$BACKEND_NAME" \
        --global \
        --network-endpoint-group="$NEG_NAME" \
        --network-endpoint-group-region="$GCP_REGION" \
        --quiet
    echo -e "${GREEN}✓ Serverless NEG attached to Backend Service!${CLEAR}"
fi

# 8. Create Google-Managed SSL Certificate
echo -e "\n${YELLOW}Step 6: Creating Google-Managed SSL Certificate...${CLEAR}"
if gcloud compute ssl-certificates describe "$SSL_CERT_NAME" --global &>/dev/null; then
    echo -e "${BLUE}SSL Certificate '$SSL_CERT_NAME' already exists.${CLEAR}"
else
    gcloud compute ssl-certificates create "$SSL_CERT_NAME" \
        --domains="$CUSTOM_DOMAIN" \
        --global \
        --quiet
    echo -e "${GREEN}✓ Google-managed SSL Certificate registered for $CUSTOM_DOMAIN!${CLEAR}"
fi

# 9. Create or Update URL Map
if [ "$OP_MODE" = "1" ]; then
    echo -e "\n${YELLOW}Step 7: Creating URL Map (Routing Rules)...${CLEAR}"
    if gcloud compute url-maps describe "$URL_MAP_NAME" --global &>/dev/null; then
        echo -e "${BLUE}URL Map '$URL_MAP_NAME' already exists. Reusing it.${CLEAR}"
    else
        gcloud compute url-maps create "$URL_MAP_NAME" \
            --default-service="$BACKEND_NAME" \
            --quiet
        echo -e "${GREEN}✓ Main URL Map '$URL_MAP_NAME' configured with default service '$BACKEND_NAME'!${CLEAR}"
    fi
else
    echo -e "\n${YELLOW}Step 7: Updating Existing URL Map '$URL_MAP_NAME' (Adding Host Routing)...${CLEAR}"
    PATH_MATCHER_NAME="pm-$RUN_SERVICE"

    # Check if path matcher already exists in this URL map
    if gcloud compute url-maps describe "$URL_MAP_NAME" --global --format="value(pathMatchers[].name)" | grep -q "$PATH_MATCHER_NAME" 2>/dev/null; then
        echo -e "${BLUE}Path matcher '$PATH_MATCHER_NAME' already exists in URL Map.${CLEAR}"
    else
        echo -e "Adding path matcher '$PATH_MATCHER_NAME'..."
        gcloud compute url-maps add-path-matcher "$URL_MAP_NAME" \
            --path-matcher-name="$PATH_MATCHER_NAME" \
            --default-service="$BACKEND_NAME" \
            --global \
            --quiet
    fi

    # Check if host rule already exists
    if gcloud compute url-maps describe "$URL_MAP_NAME" --global --format="value(hostRules[].hosts[])" | grep -q "$CUSTOM_DOMAIN" 2>/dev/null; then
        echo -e "${BLUE}Host rule for '$CUSTOM_DOMAIN' already exists in URL Map.${CLEAR}"
    else
        echo -e "Adding host rule for '$CUSTOM_DOMAIN'..."
        gcloud compute url-maps add-host-rule "$URL_MAP_NAME" \
            --hosts="$CUSTOM_DOMAIN" \
            --path-matcher-name="$PATH_MATCHER_NAME" \
            --global \
            --quiet
    fi
    echo -e "${GREEN}✓ URL Map host routing updated successfully!${CLEAR}"
fi

# 10. Create Target HTTPS Proxy
echo -e "\n${YELLOW}Step 8: Configuring Target HTTPS Proxy...${CLEAR}"
if gcloud compute target-https-proxies describe "$HTTPS_PROXY_NAME" --global &>/dev/null; then
    echo -e "${BLUE}Target HTTPS Proxy '$HTTPS_PROXY_NAME' already exists.${CLEAR}"
else
    gcloud compute target-https-proxies create "$HTTPS_PROXY_NAME" \
        --url-map="$URL_MAP_NAME" \
        --ssl-certificates="$SSL_CERT_NAME" \
        --quiet
    echo -e "${GREEN}✓ Target HTTPS Proxy created!${CLEAR}"
fi

# 11. Create HTTPS Forwarding Rule (Frontend Port 443)
echo -e "\n${YELLOW}Step 9: Opening HTTPS Frontend on Port 443...${CLEAR}"
if gcloud compute forwarding-rules describe "$HTTPS_FORWARDING_RULE" --global &>/dev/null; then
    echo -e "${BLUE}HTTPS Forwarding Rule '$HTTPS_FORWARDING_RULE' already exists.${CLEAR}"
else
    gcloud compute forwarding-rules create "$HTTPS_FORWARDING_RULE" \
        --global \
        --target-https-proxy="$HTTPS_PROXY_NAME" \
        --ports=443 \
        --address="$IP_NAME" \
        --load-balancing-scheme=EXTERNAL_MANAGED \
        --quiet
    echo -e "${GREEN}✓ HTTPS Forwarding Rule active!${CLEAR}"
fi

# 12. Create HTTP-to-HTTPS Redirect URL Map
echo -e "\n${YELLOW}Step 10: Provisioning HTTP-to-HTTPS Redirector...${CLEAR}"
if gcloud compute url-maps describe "$REDIRECT_MAP_NAME" --global &>/dev/null; then
    echo -e "${BLUE}Redirect URL Map '$REDIRECT_MAP_NAME' already exists.${CLEAR}"
else
    cat <<EOF > redirect-map.yaml
kind: compute#urlMap
name: $REDIRECT_MAP_NAME
defaultUrlRedirect:
  redirectResponseCode: MOVED_PERMANENTLY_DEFAULT
  httpsRedirect: true
EOF
    gcloud compute url-maps import "$REDIRECT_MAP_NAME" \
        --source=redirect-map.yaml \
        --global \
        --quiet
    rm -f redirect-map.yaml
    echo -e "${GREEN}✓ HTTP-to-HTTPS redirect logic defined!${CLEAR}"
fi

# 13. Create Target HTTP Proxy
echo -e "\n${YELLOW}Step 11: Configuring Target HTTP Proxy...${CLEAR}"
if gcloud compute target-http-proxies describe "$HTTP_PROXY_NAME" --global &>/dev/null; then
    echo -e "${BLUE}Target HTTP Proxy '$HTTP_PROXY_NAME' already exists.${CLEAR}"
else
    gcloud compute target-http-proxies create "$HTTP_PROXY_NAME" \
        --url-map="$REDIRECT_MAP_NAME" \
        --quiet
    echo -e "${GREEN}✓ Target HTTP Proxy created!${CLEAR}"
fi

# 14. Create HTTP Forwarding Rule (Frontend Port 80)
echo -e "\n${YELLOW}Step 12: Opening HTTP Redirect Frontend on Port 80...${CLEAR}"
if gcloud compute forwarding-rules describe "$HTTP_FORWARDING_RULE" --global &>/dev/null; then
    echo -e "${BLUE}HTTP Forwarding Rule '$HTTP_FORWARDING_RULE' already exists.${CLEAR}"
else
    gcloud compute forwarding-rules create "$HTTP_FORWARDING_RULE" \
        --global \
        --target-http-proxy="$HTTP_PROXY_NAME" \
        --ports=80 \
        --address="$IP_NAME" \
        --load-balancing-scheme=EXTERNAL_MANAGED \
        --quiet
    echo -e "${GREEN}✓ HTTP Forwarding Rule active!${CLEAR}"
fi

# 15. Add run.invoker to default Compute Engine Service Account
echo -e "\n${YELLOW}Step 13: Granting run.invoker permission on default Compute Engine service account...${CLEAR}"
GCP_PROJECT_NUMBER=$(gcloud projects describe "$GCP_PROJECT_ID" --format="value(projectNumber)")
DEFAULT_COMPUTE_SA="$GCP_PROJECT_NUMBER-compute@developer.gserviceaccount.com"

gcloud projects add-iam-policy-binding "$GCP_PROJECT_ID" \
    --member="serviceAccount:$DEFAULT_COMPUTE_SA" \
    --role="roles/run.invoker" \
    --quiet >/dev/null
echo -e "${GREEN}✓ Allowed Default Compute Engine Service Account ($DEFAULT_COMPUTE_SA) to invoke Cloud Run services!${CLEAR}"

# 16. Summary & Instructions
echo -e "\n${GREEN}======================================================================${CLEAR}"
if [ "$OP_MODE" = "1" ]; then
    echo -e "${GREEN}   LOAD BALANCER & SSL PROVISIONED SUCCESSFULLY!                       ${CLEAR}"
else
    echo -e "${GREEN}   LOAD BALANCER UPDATED & NEW ENVIRONMENT PROVISIONED!                ${CLEAR}"
fi
echo -e "${GREEN}======================================================================${CLEAR}"
echo -e "\nTo complete domain mapping, configure your Domain DNS settings:"
echo -e "\n1. Create a ${YELLOW}A Record${CLEAR} at your DNS provider (e.g. GoDaddy):"
echo -e "   - Type:    ${BLUE}A Record${CLEAR}"
echo -e "   - Name:    ${BLUE}${CUSTOM_DOMAIN}${CLEAR}"
echo -e "   - Value:   ${BLUE}${ALB_IP}${CLEAR}"
echo -e "   - TTL:     ${BLUE}Custom (e.g., 600 seconds)${CLEAR}"

echo -e "\n${YELLOW}⚠️  IMPORTANT SSL NOTICE:${CLEAR}"
echo -e "Google-managed SSL Certificates can take up to ${YELLOW}72 hours${CLEAR} to provision."
echo -e "During validation, visiting ${BLUE}https://${CUSTOM_DOMAIN}${CLEAR} may display SSL warnings."
echo -e "You can track the validation status by running:"
echo -e "   ${GREEN}gcloud compute ssl-certificates describe $SSL_CERT_NAME --global --format=\"get(managed.status)\"${CLEAR}"
echo -e "\n${BLUE}======================================================================${CLEAR}"
