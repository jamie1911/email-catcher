import React, { useEffect, useState } from "react";
import {
  Table,
  TableCell,
  TableBody,
  TableHead,
  TableRow,
  Button,
  View,
  ScrollView,
  Flex,
  Label,
  Input,
  CheckboxField,
} from "@aws-amplify/ui-react";
import { useNavigate } from "react-router-dom";
import { get, post } from 'aws-amplify/api';
import awsExports from "src/aws-exports";
import { FiPlus } from "react-icons/fi";
import { Cache } from 'aws-amplify/utils';

const EmailAccounts = () => {
  const ADDRESSES_CACHE_KEY = 'addressesCache';
  const cacheExpirationDuration = 5 * 60 * 1000; // 5 minutes
  const navigate = useNavigate();
  const [addresses, setAddresses] = useState<any[]>([])
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [newAddress, setNewAddress] = useState(String);
  const [summarizeEmails, setSummarizeEmails] = useState(Boolean);
  const handleAccountClick = (emailAddress) => {
    navigate(`/email-accounts/${encodeURIComponent(emailAddress)}`);
  };

  async function getAddresses(useCache = false) {
    setLoading(true);
    try {
      // Check cache first
      if (useCache) {
        const cachedData = await Cache.getItem(ADDRESSES_CACHE_KEY);
        if (cachedData) {
          setAddresses(cachedData);
          setLoading(false);
          return;
        }
      }

      // Fetch data from API if not cached or cache is bypassed
      const restOperation = get({
        apiName: 'disposible',
        path: 'addresses',
      });
      const { body } = await restOperation.response;
      const response = await body.json();

      if (Array.isArray(response)) {
        setAddresses(response);
        // Cache the data
        Cache.setItem(ADDRESSES_CACHE_KEY, response, { expires: new Date().getTime() + cacheExpirationDuration }); // Expires in 1800 seconds (30 minutes)
      }
    } catch (err) {
      console.error('GET call failed: ', err);
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  async function handleSubmit() {
    setLoading(true)
    try {
      const postData = {
        new_address: newAddress + `@${awsExports.emailDomain}`,
        summarize_emails: summarizeEmails,
      };
      await post({ apiName: 'disposible', path: 'addresses', options: { body: postData } });
      setAddresses(prevAddresses => [...prevAddresses, { address: newAddress + `@${awsExports.emailDomain}` }]);
      setSummarizeEmails(false);
    } catch (err) {
      console.error('POST call failed: ', err);
      setError(err);
    }
    finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    getAddresses();
  }, []);

  if (loading) return <div>Loading...</div>;
  if (error) return <div>Error fetching addresses</div>;

  return (
    <>
      <Flex className="header-flex" justifyContent="flex-start">
        <div className="email-header">
          <h2>Email Accounts</h2>
        </div>
      </Flex>
      <Flex direction="row" alignItems="center" gap="small" justifyContent="flex-end" className="form-flex">
        <Label htmlFor="new_address" className="form-label">New Address:</Label>
        <Input id="new_address" name="new_address" className="form-input" placeholder={`@${awsExports.emailDomain}`} onChange={(e) => setNewAddress(e.target.value)} />
        <CheckboxField isDisabled={loading} label="Summerize Emails" name="summarize_emails" checked={summarizeEmails} onChange={(e) => setSummarizeEmails(e.target.checked)} />
        <Button isLoading={loading} isDisabled={loading} variation="primary" className="form-button" onClick={handleSubmit}>
          <FiPlus />
        </Button>
      </Flex>
      <br></br>
      <View
        backgroundColor="var(--amplify-colors-white)"
        borderRadius="6px"
        maxWidth="100%"
        padding="1rem"
        minHeight="50vh"

      >
        <ScrollView width="100%">
          <Table highlightOnHover={true} size="small">
            <TableHead>
              <TableRow>
                <TableCell>Address</TableCell>
                <TableCell>Action</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {addresses.map((item, index) => {
                return (
                  <TableRow onClick={() => handleAccountClick(item.address)} key={index}>
                    <TableCell>{item.address}</TableCell>
                    <TableCell>
                      <Flex justifyContent="flex-start" alignItems="center">
                        <Button onClick={() => handleAccountClick(item.address)} size="small">Select</Button>
                      </Flex>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </ScrollView>
      </View >
    </>
  );
};

export default EmailAccounts;
